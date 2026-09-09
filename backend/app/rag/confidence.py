"""Confidence scoring — evaluates retrieval quality."""

from __future__ import annotations

from typing import List

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

log = get_logger(__name__)


def calculate_confidence(chunks: List[RetrievedChunk], query: str) -> float:
    """Calculate normalized confidence score (0.0–1.0) from retrieval results.

    Factors:
    1. Top chunk score (40%)
    2. Score consistency across chunks (20%)
    3. Number of supporting chunks (20%)
    4. Query term coverage in chunks (20%)
    """
    if not chunks:
        return 0.0

    # Factor 1: Top chunk score (40%)
    top_score = chunks[0].score
    factor_top = min(1.0, top_score)

    # Factor 2: Score consistency (20%) — are multiple chunks agreeing?
    if len(chunks) >= 2:
        scores = [c.score for c in chunks[:5]]
        avg_score = sum(scores) / len(scores)
        factor_consistency = min(1.0, avg_score)
    else:
        factor_consistency = factor_top * 0.5

    # Factor 3: Number of supporting chunks (20%)
    n_chunks = len(chunks)
    if n_chunks >= 4:
        factor_support = 1.0
    elif n_chunks >= 2:
        factor_support = 0.7
    elif n_chunks == 1:
        factor_support = 0.4
    else:
        factor_support = 0.0

    # Factor 4: Query term coverage (20%)
    query_terms = set(query.lower().split())
    if query_terms:
        all_text = " ".join(c.text.lower() for c in chunks[:5])
        matched = sum(1 for t in query_terms if t in all_text)
        factor_coverage = matched / len(query_terms)
    else:
        factor_coverage = 0.5

    # Weighted combination
    confidence = (
        factor_top * 0.40
        + factor_consistency * 0.20
        + factor_support * 0.20
        + factor_coverage * 0.20
    )

    confidence = round(min(1.0, max(0.0, confidence)), 4)

    log.info("Confidence: %.2f (top=%.2f, consist=%.2f, support=%.2f, coverage=%.2f)",
             confidence, factor_top, factor_consistency, factor_support, factor_coverage)
    return confidence


def is_confident_enough(confidence: float) -> bool:
    return confidence >= settings.CONFIDENCE_THRESHOLD
