"""Hybrid search — multi-strategy retrieval with Reciprocal Rank Fusion."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk
from app.rag.query_router import QueryIntent, QueryPlan

log = get_logger(__name__)


def _semantic_search(query: str, top_k: int = 20) -> List[RetrievedChunk]:
    """Dense vector search via ChromaDB embeddings."""
    from app.models.database import get_collection
    from app.services.embedding_service import EmbeddingService

    try:
        col = get_collection()
        embed_service = EmbeddingService()
        qe = embed_service.embed(query)

        results = col.query(
            query_embeddings=[qe],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        if results and results["ids"] and results["ids"][0]:
            for i, cid in enumerate(results["ids"][0]):
                dist = results["distances"][0][i]
                score = max(0.0, 1.0 - dist)
                chunks.append(RetrievedChunk(
                    chunk_id=cid,
                    document_id=results["metadatas"][0][i].get("document_id", ""),
                    text=results["documents"][0][i] or "",
                    score=score,
                    metadata=results["metadatas"][0][i],
                    source="semantic",
                ))
        return chunks
    except Exception as e:
        log.error("Semantic search failed: %s", e)
        return []


def _keyword_search(query: str, top_k: int = 20) -> List[RetrievedChunk]:
    """BM25/FTS5 keyword search."""
    from app.models.database import search_fts
    try:
        rows = search_fts(query, limit=top_k)
        chunks = []
        for row in rows:
            rank = abs(row.get("rank", 0))
            score = 1.0 / (1.0 + rank) if rank else 0.5
            chunks.append(RetrievedChunk(
                chunk_id=row.get("chunk_id", ""),
                document_id=row.get("document_id", ""),
                text=row.get("text", ""),
                score=score,
                metadata={"file_name": row.get("file_name", "")},
                source="keyword",
            ))
        return chunks
    except Exception as e:
        log.error("Keyword search failed: %s", e)
        return []


def _hydrate_metadata(chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
    """Enrich keyword-sourced chunks with full ChromaDB metadata."""
    if not chunks:
        return chunks

    from app.models.database import get_collection
    try:
        col = get_collection()
        ids_to_hydrate = [c.chunk_id for c in chunks if c.source == "keyword" and c.chunk_id]
        if not ids_to_hydrate:
            return chunks

        data = col.get(ids=ids_to_hydrate, include=["metadatas"])
        meta_map = {}
        if data and data["ids"]:
            for i, cid in enumerate(data["ids"]):
                meta_map[cid] = data["metadatas"][i]

        for chunk in chunks:
            if chunk.chunk_id in meta_map:
                chunk.metadata = meta_map[chunk.chunk_id]
        return chunks
    except Exception:
        return chunks


def _page_search(page_number: int, top_k: int = 10) -> List[RetrievedChunk]:
    """Search for chunks from a specific page number."""
    from app.models.database import get_collection
    try:
        col = get_collection()
        results = col.get(
            where={"page_number": page_number},
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
                    score=5.0,  # High priority for exact page match
                    metadata=results["metadatas"][i],
                    source="page_lookup",
                ))
        return chunks
    except Exception as e:
        log.error("Page search failed: %s", e)
        return []


def _reciprocal_rank_fusion(
    result_lists: List[List[RetrievedChunk]],
    k: int = 60,
) -> List[RetrievedChunk]:
    """Merge multiple ranked result lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum(1 / (k + rank_i)) across all lists where the item appears.
    """
    fused_scores: Dict[str, float] = {}
    chunk_map: Dict[str, RetrievedChunk] = {}

    for result_list in result_lists:
        for rank, chunk in enumerate(result_list):
            cid = chunk.chunk_id
            if not cid:
                continue
            rrf_score = 1.0 / (k + rank + 1)
            fused_scores[cid] = fused_scores.get(cid, 0.0) + rrf_score

            # Keep the version with the highest original score / most metadata
            if cid not in chunk_map or len(chunk.metadata) > len(chunk_map[cid].metadata):
                chunk_map[cid] = chunk

    # Sort by RRF score
    sorted_ids = sorted(fused_scores.keys(), key=lambda x: fused_scores[x], reverse=True)

    merged = []
    for cid in sorted_ids:
        chunk = chunk_map[cid]
        chunk.score = fused_scores[cid]
        merged.append(chunk)

    return merged


def hybrid_search(
    query: str,
    plan: Optional[QueryPlan] = None,
    top_k: int = None,
) -> Tuple[List[RetrievedChunk], int, int]:
    """Multi-strategy hybrid search with RRF fusion.

    Returns (merged_chunks, semantic_count, keyword_count).
    """
    top_k = top_k or settings.TOP_K
    result_lists: List[List[RetrievedChunk]] = []
    semantic_count = 0
    keyword_count = 0

    # ── Identifier search (highest priority) ──────────
    identifier_results = []
    if plan and plan.identifiers:
        from app.rag.identifier_search import identifier_search
        identifier_results = identifier_search(plan.identifiers, top_k=top_k)
        if identifier_results:
            result_lists.append(identifier_results)
            log.info("Identifier search: %d results", len(identifier_results))

    # ── Page lookup ───────────────────────────────────
    if plan and plan.target_page:
        page_results = _page_search(plan.target_page, top_k=top_k)
        if page_results:
            result_lists.append(page_results)
            log.info("Page search (page %d): %d results", plan.target_page, len(page_results))

    # Determine the effective search query
    search_query = query
    if plan and plan.resolved_query:
        search_query = plan.resolved_query

    # ── Skip expensive search if exact identifier fully satisfied ──
    skip_broad_search = (
        plan and
        plan.intent in (QueryIntent.EXACT_IDENTIFIER,) and
        len(identifier_results) >= 1
    )

    if not skip_broad_search:
        # ── BM25 / FTS5 keyword search ───────────────
        kw_results = _keyword_search(search_query, top_k=top_k)
        kw_results = _hydrate_metadata(kw_results)
        keyword_count = len(kw_results)
        if kw_results:
            result_lists.append(kw_results)

        # ── Dense vector search ──────────────────────
        sem_results = _semantic_search(search_query, top_k=top_k)
        semantic_count = len(sem_results)
        if sem_results:
            result_lists.append(sem_results)

    # ── Fusion ───────────────────────────────────────
    if not result_lists:
        return [], 0, 0

    if len(result_lists) == 1:
        merged = result_lists[0]
    else:
        merged = _reciprocal_rank_fusion(result_lists)

    # ── Identifier boost (ensure exact matches are on top) ──
    if plan and plan.identifiers:
        canonical_ids = set()
        for ident in plan.identifiers:
            canonical_ids.add(re.sub(r'[\s\-_]', '', ident).upper())

        for chunk in merged:
            text_upper = chunk.text.upper().replace(" ", "").replace("-", "").replace("_", "")
            meta_id = str(chunk.metadata.get("identifier", "")).upper().replace(" ", "").replace("-", "").replace("_", "")
            meta_ps = str(chunk.metadata.get("ps_code", "")).upper().replace(" ", "").replace("-", "").replace("_", "")

            for cid in canonical_ids:
                if cid in text_upper or cid == meta_id or cid == meta_ps:
                    chunk.score += 5.0
                    break

    # Re-sort after boost
    merged.sort(key=lambda c: c.score, reverse=True)

    log.info(
        "Hybrid search: %d merged results (semantic=%d, keyword=%d, identifier=%d)",
        len(merged), semantic_count, keyword_count, len(identifier_results),
    )
    return merged[:top_k * 2], semantic_count, keyword_count
