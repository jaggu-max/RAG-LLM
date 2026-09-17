"""Identifier Search — exact retrieval for document identifiers (SIH codes, etc.)."""

from __future__ import annotations

import re    
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

log = get_logger(__name__)


def search_structured_records(identifier: str) -> List[Dict[str, Any]]:
    """Search the structured_records SQLite table for an exact identifier match."""
    from app.models.database import _get_conn
    conn = _get_conn()
    try:
        # Normalize: uppercase, strip separators
        canonical = re.sub(r'[\s\-_]', '', identifier).upper()

        rows = conn.execute(
            """SELECT * FROM structured_records
               WHERE UPPER(REPLACE(REPLACE(REPLACE(identifier, ' ', ''), '-', ''), '_', '')) = ?
               OR UPPER(REPLACE(REPLACE(REPLACE(ps_code, ' ', ''), '-', ''), '_', '')) = ?""",
            (canonical, canonical),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.debug("structured_records search failed (table may not exist yet): %s", e)
        return []
    finally:
        conn.close()


def search_chroma_by_identifier(identifier: str, top_k: int = 10) -> List[RetrievedChunk]:
    """Search ChromaDB metadata for an identifier match."""
    from app.models.database import get_collection
    try:
        col = get_collection()
        canonical = re.sub(r'[\s\-_]', '', identifier).upper()

        # ChromaDB $contains filter on metadata.identifier
        results = col.get(
            where={"identifier": canonical},
            limit=top_k,
            include=["documents", "metadatas"],
        )

        chunks = []
        if results and results["ids"]:
            for i, cid in enumerate(results["ids"]):
                chunks.append(RetrievedChunk(
                    chunk_id=cid,
                    document_id=results["metadatas"][i].get("document_id", ""),
                    text=results["documents"][i] or "",
                    score=10.0,  # Highest priority
                    metadata=results["metadatas"][i],
                    source="identifier_exact",
                ))
        return chunks
    except Exception as e:
        log.debug("ChromaDB identifier search failed: %s", e)
        return []


def search_fts_for_identifier(identifier: str, top_k: int = 10) -> List[RetrievedChunk]:
    """Search FTS5 for chunks containing the identifier."""
    from app.models.database import _get_conn
    conn = _get_conn()
    try:
        canonical = re.sub(r'[\s\-_]', '', identifier).upper()
        # Also try with original casing
        variants = {canonical, identifier.upper(), identifier}

        all_rows = []
        for variant in variants:
            safe = variant.replace('"', '""')
            try:
                rows = conn.execute(
                    """SELECT chunk_id, document_id, text, file_name, rank
                       FROM chunks_fts
                       WHERE chunks_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (f'"{safe}"', top_k),
                ).fetchall()
                all_rows.extend(rows)
            except Exception:
                pass

        # Deduplicate by chunk_id
        seen = set()
        chunks = []
        for row in all_rows:
            r = dict(row)
            cid = r.get("chunk_id", "")
            if cid in seen or not cid:
                continue
            seen.add(cid)

            # Check text actually contains the identifier (case-insensitive)
            text = r.get("text", "")
            text_upper = text.upper().replace(" ", "").replace("-", "").replace("_", "")
            if canonical in text_upper:
                score = 8.0  # Very high priority for exact text match
            else:
                score = 3.0  # Lower if FTS matched but text doesn't contain exact ID

            chunks.append(RetrievedChunk(
                chunk_id=cid,
                document_id=r.get("document_id", ""),
                text=text,
                score=score,
                metadata={"file_name": r.get("file_name", "")},
                source="identifier_fts",
            ))

        return chunks
    except Exception as e:
        log.debug("FTS identifier search failed: %s", e)
        return []
    finally:
        conn.close()


def hydrate_chunks_from_chroma(chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """Enrich FTS-sourced chunks with full metadata from ChromaDB."""
    if not chunks:
        return chunks

    from app.models.database import get_collection
    try:
        col = get_collection()
        ids_to_hydrate = [c.chunk_id for c in chunks if c.source == "identifier_fts" and c.chunk_id]
        if not ids_to_hydrate:
            return chunks

        data = col.get(ids=ids_to_hydrate, include=["metadatas", "documents"])
        meta_map = {}
        text_map = {}
        if data and data["ids"]:
            for i, cid in enumerate(data["ids"]):
                meta_map[cid] = data["metadatas"][i]
                text_map[cid] = data["documents"][i]

        for chunk in chunks:
            if chunk.chunk_id in meta_map:
                chunk.metadata = meta_map[chunk.chunk_id]
                if text_map.get(chunk.chunk_id):
                    chunk.text = text_map[chunk.chunk_id]

        return chunks
    except Exception as e:
        log.debug("ChromaDB hydration failed: %s", e)
        return chunks


def identifier_search(identifiers: List[str], top_k: int = 10) -> List[RetrievedChunk]:
    """Multi-strategy identifier search: structured_records → ChromaDB metadata → FTS5.

    Returns merged, deduplicated results sorted by score.
    """
    all_chunks: List[RetrievedChunk] = []
    seen_ids: set = set()

    for ident in identifiers:
        log.info("Identifier search for: %s", ident)

        # Strategy 1: Structured records table
        records = search_structured_records(ident)
        if records:
            log.info("Found %d structured records for %s", len(records), ident)
            for rec in records:
                # Build a rich text representation from the structured record
                text_parts = []
                for field_name in ["ps_code", "track", "problem_statement_title", "problem_statement",
                                   "theme", "sponsoring_ministry", "page_number"]:
                    val = rec.get(field_name)
                    if val:
                        label = field_name.replace("_", " ").title()
                        text_parts.append(f"{label}: {val}")
                if rec.get("raw_text"):
                    text_parts.append(rec["raw_text"])

                chunk = RetrievedChunk(
                    chunk_id=rec.get("id", ""),
                    document_id=rec.get("document_id", ""),
                    text="\n".join(text_parts),
                    score=10.0,
                    metadata={
                        "file_name": rec.get("source_document", ""),
                        "page_number": rec.get("page_number"),
                        "identifier": rec.get("identifier", ""),
                        "ps_code": rec.get("ps_code", ""),
                        "record_type": "structured",
                        **{k: v for k, v in rec.items() if k not in ("raw_text", "id", "document_id", "created_at")},
                    },
                    source="structured_record",
                )
                if chunk.chunk_id not in seen_ids:
                    seen_ids.add(chunk.chunk_id)
                    all_chunks.append(chunk)

        # Strategy 2: ChromaDB metadata filter
        chroma_results = search_chroma_by_identifier(ident, top_k)
        for chunk in chroma_results:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                all_chunks.append(chunk)

        # Strategy 3: FTS5 keyword search
        fts_results = search_fts_for_identifier(ident, top_k)
        fts_results = hydrate_chunks_from_chroma(fts_results)
        for chunk in fts_results:
            if chunk.chunk_id not in seen_ids:
                seen_ids.add(chunk.chunk_id)
                all_chunks.append(chunk)

    # Sort by score descending
    all_chunks.sort(key=lambda c: c.score, reverse=True)
    return all_chunks[:top_k]
