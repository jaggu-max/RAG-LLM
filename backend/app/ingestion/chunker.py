"""Intelligent text chunker with overlap, preserving structure."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Tuple

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def chunk_text(
    text: str,
    metadata: Dict[str, Any],
    document_id: str,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> List[Dict[str, Any]]:
    """Split text into overlapping chunks preserving paragraph boundaries.

    Returns list of dicts with: chunk_id, document_id, text, metadata.
    """
    chunk_size = chunk_size or settings.CHUNK_SIZE
    chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

    if not text.strip():
        return []

    # Try to split on paragraph boundaries first
    paragraphs = text.split("\n\n")
    chunks: List[Dict[str, Any]] = []
    current_chunk = ""
    chunk_index = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If single paragraph is larger than chunk_size, split it
        if len(para) > chunk_size:
            # Flush current chunk first
            if current_chunk.strip():
                chunks.append(_make_chunk(
                    current_chunk.strip(), metadata, document_id, chunk_index
                ))
                chunk_index += 1

            # Split large paragraph by sentences
            sub_chunks = _split_large_text(para, chunk_size, chunk_overlap)
            for sc in sub_chunks:
                chunks.append(_make_chunk(sc, metadata, document_id, chunk_index))
                chunk_index += 1
            current_chunk = ""
            continue

        # Check if adding the paragraph exceeds chunk_size
        candidate = (current_chunk + "\n\n" + para).strip() if current_chunk else para
        if len(candidate) > chunk_size:
            # Save current chunk
            if current_chunk.strip():
                chunks.append(_make_chunk(
                    current_chunk.strip(), metadata, document_id, chunk_index
                ))
                chunk_index += 1

            # Start new chunk with overlap
            overlap_text = _get_overlap(current_chunk, chunk_overlap)
            current_chunk = (overlap_text + "\n\n" + para).strip() if overlap_text else para
        else:
            current_chunk = candidate

    # Don't forget the last chunk
    if current_chunk.strip():
        chunks.append(_make_chunk(
            current_chunk.strip(), metadata, document_id, chunk_index
        ))

    log.info("Chunked document %s → %d chunks", document_id[:8], len(chunks))
    return chunks


def _make_chunk(text: str, metadata: Dict[str, Any],
                document_id: str, index: int) -> Dict[str, Any]:
    chunk_id = f"{document_id}_{index}_{uuid.uuid4().hex[:6]}"
    chunk_meta = {**metadata}
    chunk_meta["chunk_id"] = chunk_id
    chunk_meta["document_id"] = document_id
    chunk_meta["chunk_index"] = index
    # Ensure all metadata values are simple types for ChromaDB
    for k, v in list(chunk_meta.items()):
        if v is None:
            chunk_meta[k] = ""
        elif not isinstance(v, (str, int, float, bool)):
            chunk_meta[k] = str(v)
    return {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "text": text,
        "metadata": chunk_meta,
        "file_name": metadata.get("file_name", ""),
    }


def _split_large_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text that's too large for a single chunk."""
    # Try sentence boundaries
    sentences = text.replace(". ", ".\n").split("\n")
    chunks = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        candidate = (current + " " + sent).strip() if current else sent
        if len(candidate) > chunk_size and current:
            chunks.append(current.strip())
            overlap_text = _get_overlap(current, overlap)
            current = (overlap_text + " " + sent).strip() if overlap_text else sent
        else:
            current = candidate

    if current.strip():
        chunks.append(current.strip())

    # Fallback: hard split if we still have chunks that are too large
    final = []
    for c in chunks:
        if len(c) > chunk_size * 2:
            for i in range(0, len(c), chunk_size - overlap):
                final.append(c[i : i + chunk_size])
        else:
            final.append(c)

    return final


def _get_overlap(text: str, overlap_chars: int) -> str:
    """Get the last `overlap_chars` characters for chunk overlap."""
    if not text or overlap_chars <= 0:
        return ""
    return text[-overlap_chars:].strip()
