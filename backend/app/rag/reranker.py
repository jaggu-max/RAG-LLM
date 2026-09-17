"""Cross-encoder reranker — re-scores query-document pairs with identifier awareness."""

from __future__ import annotations

import re
from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk
from app.rag.query_router import QueryPlan

log = get_logger(__name__)

_reranker_model = None


def _load_reranker():
    global _reranker_model
    if _reranker_model is None:
        log.info("Loading cross-encoder reranker...")
        from sentence_transformers import CrossEncoder
        _reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        log.info("✓ Reranker loaded")
    return _reranker_model


def rerank(
    query: str,
    chunks: List[RetrievedChunk],
    plan: Optional[QueryPlan] = None,
    top_k: int | None = None,
) -> List[RetrievedChunk]:
    """Re-rank chunks using cross-encoder, with identifier-aware boosting."""
    top_k = top_k or settings.FINAL_TOP_K

    if not chunks:
        return []

    # ── Step 1: Separate exact-match chunks from the rest ──
    exact_chunks = []
    scorable_chunks = []

    canonical_ids = set()
    if plan and plan.identifiers:
        for ident in plan.identifiers:
            canonical_ids.add(re.sub(r'[\s\-_]', '', ident).upper())

    for chunk in chunks:
        is_exact = False
        if canonical_ids:
            text_upper = chunk.text.upper().replace(" ", "").replace("-", "").replace("_", "")
            meta_id = str(chunk.metadata.get("identifier", "")).upper().replace(" ", "")
            meta_ps = str(chunk.metadata.get("ps_code", "")).upper().replace(" ", "")

            for cid in canonical_ids:
                if cid == meta_id or cid == meta_ps or (cid in text_upper and chunk.source in ("structured_record", "identifier_exact", "identifier_fts")):
                    is_exact = True
                    break

        if is_exact:
            exact_chunks.append(chunk)
        else:
            scorable_chunks.append(chunk)

    # ── Step 2: Cross-encoder reranking on non-exact chunks ──
    if settings.RERANKER_ENABLED and scorable_chunks:
        try:
            model = _load_reranker()
            pairs = [(query, chunk.text) for chunk in scorable_chunks]
            scores = model.predict(pairs)

            for i, chunk in enumerate(scorable_chunks):
                chunk.score = float(scores[i])

            scorable_chunks.sort(key=lambda c: c.score, reverse=True)

            # Normalize scores to 0-1
            if scorable_chunks:
                max_s = max(c.score for c in scorable_chunks)
                min_s = min(c.score for c in scorable_chunks)
                rng = max_s - min_s if max_s != min_s else 1.0
                for c in scorable_chunks:
                    c.score = round((c.score - min_s) / rng, 4)
        except Exception as e:
            log.error("Reranker failed: %s — falling back to original order", e)

    # ── Step 3: Exact matches always on top with score = 1.0 ──
    for chunk in exact_chunks:
        chunk.score = 1.0

    # Combine: exact first, then reranked
    result = exact_chunks + scorable_chunks
    result = result[:top_k]

    log.info("Reranked %d → %d chunks (exact=%d)", len(chunks), len(result), len(exact_chunks))
    return result


def is_reranker_available() -> bool:
    try:
        _load_reranker()
        return True
    except Exception:
        return False
