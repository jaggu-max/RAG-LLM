"""Context builder — assembles retrieved chunks into LLM-ready context."""

from __future__ import annotations

from typing import List

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

log = get_logger(__name__)


def build_context(chunks: List[RetrievedChunk], max_chars: int | None = None) -> str:
    """Assemble top chunks into a formatted context string.

    Deduplicates, caps at max_chars, and adds source annotations.
    """
    max_chars = max_chars or settings.MAX_CONTEXT_CHARS
    if not chunks:
        return ""

    context_parts: List[str] = []
    seen_texts: set = set()
    total_chars = 0

    for i, chunk in enumerate(chunks):
        # Deduplicate by first 200 chars
        text_key = chunk.text[:200]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        # Build source annotation
        source_label = chunk.metadata.get("file_name", "Unknown")
        page = chunk.metadata.get("page_number", "")
        sheet = chunk.metadata.get("sheet_name", "")
        section = chunk.metadata.get("section", "")

        source_info = f"[Source: {source_label}"
        if page:
            source_info += f", Page {page}"
        if sheet:
            source_info += f", Sheet: {sheet}"
        if section:
            source_info += f", Section: {section}"
        source_info += f", Relevance: {chunk.score:.0%}]"

        entry = f"--- Evidence {i+1} {source_info} ---\n{chunk.text}"

        if total_chars + len(entry) > max_chars:
            # Try to fit a truncated version
            remaining = max_chars - total_chars - 100
            if remaining > 200:
                entry = entry[:remaining] + "..."
                context_parts.append(entry)
            break

        context_parts.append(entry)
        total_chars += len(entry)

    context = "\n\n".join(context_parts)

    log.info("Context built: %d chunks, %d chars", len(context_parts), len(context))
    return context
