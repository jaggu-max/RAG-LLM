"""Confidence scorer — calculates retrieval confidence with identifier awareness."""

from __future__ import annotations

import re
from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk
from app.rag.query_router import QueryIntent, QueryPlan

log = get_logger(__name__)


def calculate_confidence(
    chunks: List[RetrievedChunk],
    query: str,
    plan: Optional[QueryPlan] = None,
) -> float:
    """Calculate overall retrieval confidence."""
    if not chunks:
        return 0.0

    # ── Check for exact identifier matches ──
    has_exact_match = False
    has_structured_record = False

    canonical_ids = set()
    if plan and plan.identifiers:
        for ident in plan.identifiers:
            canonical_ids.add(re.sub(r'[\s\-_]', '', ident).upper())
    else:
        # Extract from query as fallback
        from app.rag.query_router import extract_identifiers
        ids = extract_identifiers(query)
        for ident in ids:
            canonical_ids.add(re.sub(r'[\s\-_]', '', ident).upper())

    if canonical_ids:
        for chunk in chunks:
            text_upper = chunk.text.upper().replace(" ", "").replace("-", "").replace("_", "")
            meta_id = str(chunk.metadata.get("identifier", "")).upper().replace(" ", "")
            meta_ps = str(chunk.metadata.get("ps_code", "")).upper().replace(" ", "")

            for cid in canonical_ids:
                if cid == meta_id or cid == meta_ps or cid in text_upper:
                    has_exact_match = True
                    if chunk.source == "structured_record":
                        has_structured_record = True
                    break

    # ── IMAGE_NOTE intent boost ──
    if plan and plan.intent == QueryIntent.IMAGE_NOTE:
        return 0.92

    # ── Exact identifier → very high confidence ──
    if has_structured_record:
        return 0.98

    if has_exact_match:
        return 0.95

    # ── Standard confidence calculation ──
    if not chunks:
        return 0.0

    top_score = chunks[0].score
    avg_score = sum(c.score for c in chunks[:5]) / min(len(chunks), 5)

    # Weight: top score matters most
    confidence = top_score * 0.6 + avg_score * 0.4

    # Penalty for very few results
    if len(chunks) == 1:
        confidence *= 0.85
    elif len(chunks) == 2:
        confidence *= 0.92

    # Single-word query boost (user knows what they want)
    if len(query.strip().split()) <= 2 and top_score > 0.5:
        confidence = max(confidence, 0.80)

    # Clamp
    confidence = max(0.0, min(1.0, confidence))

    return round(confidence, 4)


def is_confident_enough(confidence: float) -> bool:
    """Check if confidence meets the threshold."""
    return confidence >= settings.CONFIDENCE_THRESHOLD
