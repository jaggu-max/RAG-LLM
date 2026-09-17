"""Context builder — assembles retrieved chunks into LLM-ready context with structured record support."""

from __future__ import annotations

from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk
from app.rag.query_router import QueryPlan, QueryIntent

log = get_logger(__name__)


def _format_structured_record(chunk: RetrievedChunk) -> str:
    """Format a structured record chunk into labeled fields."""
    meta = chunk.metadata
    parts = []

    # Standard SIH-style fields
    field_order = [
        ("ps_code", "PS Code"),
        ("track", "Track"),
        ("problem_statement_title", "Problem Statement Title"),
        ("theme", "Theme"),
        ("sponsoring_ministry", "Sponsoring Organization / Ministry"),
        ("problem_statement", "Problem Statement"),
    ]

    for field_key, label in field_order:
        val = meta.get(field_key)
        if val and str(val).strip():
            parts.append(f"{label}: {val}")

    # Page and source
    page = meta.get("page_number")
    fname = meta.get("file_name") or meta.get("source_document", "")
    if fname:
        source_line = f"Source: {fname}"
        if page:
            source_line += f", Page {page}"
        parts.append(source_line)

    if parts:
        return "\n".join(parts)

    # Fallback to raw text
    return chunk.text


def build_context(
    chunks: List[RetrievedChunk],
    plan: Optional[QueryPlan] = None,
    max_chars: int | None = None,
) -> str:
    """Assemble top chunks into a formatted context string.

    Uses structured formatting for identifier queries, standard evidence
    assembly for semantic queries.
    """
    max_chars = max_chars or settings.MAX_CONTEXT_CHARS
    if not chunks:
        return ""

    is_identifier_query = plan and plan.intent in (
        QueryIntent.EXACT_IDENTIFIER,
        QueryIntent.IDENTIFIER_DETAIL,
        QueryIntent.COMPARISON,
    )

    context_parts: List[str] = []
    seen_texts: set = set()
    total_chars = 0

    for i, chunk in enumerate(chunks):
        # Deduplicate by first 200 chars
        text_key = chunk.text[:200]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        # Format entry based on chunk type
        if is_identifier_query and chunk.metadata.get("record_type") == "structured":
            entry = f"--- Record {i+1} ---\n{_format_structured_record(chunk)}"
        else:
            # Standard evidence format
            source_label = chunk.metadata.get("file_name", "Unknown")
            page = chunk.metadata.get("page_number", "")
            slide = chunk.metadata.get("slide_number", "")
            sheet = chunk.metadata.get("sheet_name", "")
            section = chunk.metadata.get("section", "")

            source_info = f"[Source: {source_label}"
            if slide:
                source_info += f", Slide {slide}"
            elif page:
                source_info += f", Page {page}"
            if sheet:
                source_info += f", Sheet: {sheet}"
            if section:
                source_info += f", Section: {section}"
            source_info += "]"

            entry = f"--- Evidence {i+1} {source_info} ---\n{chunk.text}"

        if total_chars + len(entry) > max_chars:
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
