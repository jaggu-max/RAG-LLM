"""Retriever — semantic search via ChromaDB."""

from __future__ import annotations

from typing import Any, Dict, List

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import query_chroma
from app.models.schemas import RetrievedChunk
from app.services.embedding_service import EmbeddingService

log = get_logger(__name__)


def semantic_search(query: str, top_k: int | None = None) -> List[RetrievedChunk]:
    """Perform semantic similarity search against ChromaDB."""
    top_k = top_k or settings.TOP_K

    embed_service = EmbeddingService()
    query_embedding = embed_service.embed(query)

    results = query_chroma(query_embedding, n_results=top_k)

    chunks: List[RetrievedChunk] = []
    if not results or not results.get("ids") or not results["ids"][0]:
        return chunks

    ids = results["ids"][0]
    documents = results["documents"][0] if results.get("documents") else [""] * len(ids)
    metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(ids)
    distances = results["distances"][0] if results.get("distances") else [1.0] * len(ids)

    for i, chunk_id in enumerate(ids):
        # Convert cosine distance to similarity (ChromaDB returns distance)
        similarity = max(0.0, 1.0 - distances[i])
        meta = metadatas[i] if i < len(metadatas) else {}
        if meta is None:
            meta = {}

        chunks.append(RetrievedChunk(
            chunk_id=chunk_id or "",
            document_id=meta.get("document_id") or "",
            text=(documents[i] if i < len(documents) else "") or "",
            score=round(similarity, 4),
            metadata=meta,
            source="semantic",
        ))

    log.info("Semantic search: %d results for query: %.50s...", len(chunks), query)
    return chunks
