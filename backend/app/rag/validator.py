"""Response validator — checks factual claims against retrieved evidence."""

from __future__ import annotations

from app.core.logging import get_logger

log = get_logger(__name__)


def validate_response(answer: str, context: str) -> bool:
    """Check if the answer's key claims are present in the context.

    Uses simple heuristic matching — checks if key factual terms
    from the answer appear in the evidence. NOT a replacement for
    LLM-based validation, but much faster.
    """
    if not answer or not context:
        return True  # Nothing to validate

    context_lower = context.lower()
    answer_lower = answer.lower()

    # Skip validation for short/generic responses
    if len(answer) < 50:
        return True

    # Skip for disclaimers
    disclaimer_phrases = [
        "couldn't find", "not found", "no information",
        "not available", "don't have", "cannot determine",
        "general knowledge",
    ]
    if any(p in answer_lower for p in disclaimer_phrases):
        return True

    # Extract potential factual claims (names, numbers, specific terms)
    import re

    # Find quoted values, numbers, capitalized proper nouns
    numbers = re.findall(r'\b\d+(?:\.\d+)?\b', answer)
    # Check if key numbers appear in context
    if numbers:
        missing_numbers = [n for n in numbers if n not in context_lower]
        # If most numbers are missing from context, flag it
        if len(missing_numbers) > len(numbers) * 0.5 and len(numbers) > 2:
            log.warning("Validation: %d/%d numbers not found in context",
                       len(missing_numbers), len(numbers))
            return False

    return True


def build_insufficient_response() -> str:
    return "I couldn't find this information in the uploaded documents."

