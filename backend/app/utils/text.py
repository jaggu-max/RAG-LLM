"""Text utilities — cleaning, normalization."""

from __future__ import annotations

import re
import unicodedata


def clean_text(text: str) -> str:
    """Normalize whitespace and remove control characters."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\r", "\n", text)
    text = re.sub(r" +", " ", text)  # collapse multiple spaces
    text = re.sub(r"\n{3,}", "\n\n", text)  # collapse excessive newlines
    return text.strip()


def truncate(text: str, max_chars: int = 2000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."
