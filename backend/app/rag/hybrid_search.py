"""Hybrid search — combines semantic (vector) + keyword (FTS5) retrieval."""

from __future__ import annotations

from typing import Dict, List

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import search_fts
from app.models.schemas import RetrievedChunk
from app.rag.retriever import semantic_search

log = get_logger(__name__)


def hybrid_search(
    query: str,
    top_k: int | None = None,
    semantic_weight: float | None = None,
    keyword_weight: float | None = None,
) -> tuple[List[RetrievedChunk], int, int]:
    """Perform hybrid search combining semantic + keyword results.

    Returns: (merged_results, semantic_count, keyword_count)
    """
    top_k = top_k or settings.TOP_K
    semantic_weight = semantic_weight or settings.SEMANTIC_WEIGHT
    keyword_weight = keyword_weight or settings.KEYWORD_WEIGHT

    # 1. Semantic search
    semantic_results = semantic_search(query, top_k=top_k)
    semantic_count = len(semantic_results)

    # 2. Keyword search (FTS5)
    keyword_raw = search_fts(query, limit=top_k)
    keyword_count = len(keyword_raw)

    # Build keyword results as RetrievedChunk
    keyword_results: List[RetrievedChunk] = []
    for i, row in enumerate(keyword_raw):
        # FTS5 rank is negative (more negative = better match)
        rank = abs(row.get("rank", 0))
        # Normalize rank to 0-1 score (heuristic)
        score = min(1.0, 1.0 / (1.0 + rank * 0.1)) if rank else 0.5
        keyword_results.append(RetrievedChunk(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            text=row.get("text", ""),
            score=round(score, 4),
            metadata={"file_name": row.get("file_name", "")},
            source="keyword",
        ))

    # 3. Merge with weighted scoring
    score_map: Dict[str, float] = {}
    chunk_map: Dict[str, RetrievedChunk] = {}

    for chunk in semantic_results:
        cid = chunk.chunk_id
        score_map[cid] = chunk.score * semantic_weight
        chunk_map[cid] = chunk

    for chunk in keyword_results:
        cid = chunk.chunk_id
        if cid in score_map:
            # Boost: appears in both
            score_map[cid] += chunk.score * keyword_weight
        else:
            score_map[cid] = chunk.score * keyword_weight
            chunk_map[cid] = chunk

    # 4. Sort by combined score
    sorted_ids = sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)

    merged: List[RetrievedChunk] = []
    seen_texts: set = set()

    for cid in sorted_ids[:top_k]:
        chunk = chunk_map[cid]
        # Deduplicate by text content
        text_key = chunk.text[:200]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        chunk.score = round(score_map[cid], 4)
        merged.append(chunk)

    log.info("Hybrid search: %d semantic + %d keyword → %d merged",
             semantic_count, keyword_count, len(merged))
    return merged, semantic_count, keyword_count
