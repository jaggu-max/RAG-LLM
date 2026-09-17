"""Query Router — normalizes queries, detects identifiers, classifies intent."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from app.core.logging import get_logger

log = get_logger(__name__)     
   

class QueryIntent(str, Enum):
    EXACT_IDENTIFIER = "exact_identifier"
    IDENTIFIER_DETAIL = "identifier_detail"
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    TABLE_LIST = "table_list"
    PAGE_LOOKUP = "page_lookup"
    COMPARISON = "comparison"
    FOLLOW_UP = "follow_up"
    SUMMARY = "summary"
    GENERAL = "general"


@dataclass
class QueryPlan:
    original_query: str
    normalized_query: str
    identifiers: List[str] = field(default_factory=list)
    intent: QueryIntent = QueryIntent.SEMANTIC
    target_fields: List[str] = field(default_factory=list)
    target_page: Optional[int] = None
    is_follow_up: bool = False
    resolved_query: Optional[str] = None
    comparison_ids: List[str] = field(default_factory=list)


# ── Identifier Patterns ─────────────────────────────────────

# SIH-style: SIH26037, SIH 26037, SIH-26037, SIH_26037, sih26037
_SIH_PATTERN = re.compile(
    r'\b[Ss][Ii][Hh]\s*[-_]?\s*(\d{4,6})\b'
)

# Generic alphanumeric ID: DOC123, ABC-2026-001, EMP102, ROLL123, PS102
_GENERIC_ID_PATTERN = re.compile(
    r'\b([A-Za-z]{2,8}[-_]?\d{3,8}(?:[-_]\d{1,6})?)\b'
)

# Bare number that could be a code suffix (e.g., "26037" alone)
_BARE_NUMBER_PATTERN = re.compile(r'\b(\d{5,6})\b')

# Page extraction: "page 4", "p. 31", "4th page"
_PAGE_PATTERN_CARDINAL = re.compile(r'\b(?:page|p\.?)\s*(\d+)\b', re.I)
_PAGE_PATTERN_ORDINAL = re.compile(r'\b(\d+)(?:st|nd|rd|th)\s*page\b', re.I)

# Follow-up pronouns
_FOLLOW_UP_WORDS = {"it", "its", "this", "that", "the same", "above", "previous"}

# Field keywords mapping
_FIELD_KEYWORDS = {
    "title": ["title", "name of", "called"],
    "track": ["track", "category"],
    "theme": ["theme", "domain", "area"],
    "sponsor": ["sponsor", "sponsors", "sponsoring", "ministry", "organization", "organisation", "funded by", "who sponsors"],
    "problem_statement": ["problem statement", "full problem", "describe the problem", "detailed problem", "complete problem", "give me the problem"],
}

# List/table intent keywords
_LIST_KEYWORDS = ["list all", "show all", "how many", "count", "all problems", "all records", "all entries"]
_SUMMARY_KEYWORDS = ["summarize", "summary", "summarise", "main points", "overview", "what is this document about"]
_COMPARISON_KEYWORDS = ["compare", "difference between", "versus", "vs"]


def extract_identifiers(query: str) -> List[str]:
    """Extract all identifiers from query text."""
    identifiers = []

    # SIH-style identifiers (normalize to SIHxxxxx)
    for match in _SIH_PATTERN.finditer(query):
        num = match.group(1)
        canonical = f"SIH{num}"
        if canonical not in identifiers:
            identifiers.append(canonical)

    # Generic alphanumeric IDs
    for match in _GENERIC_ID_PATTERN.finditer(query):
        raw = match.group(1).upper().replace("-", "").replace("_", "")
        # Skip if it's a common word or already captured as SIH
        if raw in identifiers or any(raw.startswith(s) for s in ["SIH"]):
            continue
        # Only include if it looks like a real identifier (has both letters and digits)
        if re.search(r'[A-Z]', raw) and re.search(r'\d', raw):
            original = match.group(1).upper()
            if original not in identifiers:
                identifiers.append(original)

    # Bare numbers (only if no other IDs found and query is very short)
    if not identifiers and len(query.split()) <= 3:
        for match in _BARE_NUMBER_PATTERN.finditer(query):
            num = match.group(1)
            identifiers.append(num)

    return identifiers


def extract_target_page(query: str) -> Optional[int]:
    """Extract page number from query."""
    m = _PAGE_PATTERN_ORDINAL.search(query)
    if m:
        return int(m.group(1))
    m = _PAGE_PATTERN_CARDINAL.search(query)
    if m:
        return int(m.group(1))
    return None


def detect_target_fields(query: str) -> List[str]:
    """Detect which specific fields the user is asking about."""
    q_lower = query.lower()
    fields = []
    for field_name, keywords in _FIELD_KEYWORDS.items():
        if any(kw in q_lower for kw in keywords):
            fields.append(field_name)
    return fields


def detect_follow_up(query: str) -> bool:
    """Check if query likely references a previous conversation item."""
    q_lower = query.lower().strip()
    words = set(q_lower.split())
    # Short queries with pronouns are follow-ups
    if len(q_lower.split()) <= 8 and words & _FOLLOW_UP_WORDS:
        return True
    # Questions that start with "what is its", "who sponsors it", etc.
    if any(q_lower.startswith(p) for p in ["what is its", "who sponsors it", "what is the theme", "what track", "give me the"]):
        return True
    return False


def classify_intent(query: str, identifiers: List[str], target_fields: List[str],
                    target_page: Optional[int], is_follow_up: bool) -> QueryIntent:
    """Classify the primary intent of the query."""
    q_lower = query.lower().strip()

    # Comparison: "compare X and Y"
    if any(kw in q_lower for kw in _COMPARISON_KEYWORDS) and len(identifiers) >= 2:
        return QueryIntent.COMPARISON

    # Follow-up
    if is_follow_up and not identifiers:
        return QueryIntent.FOLLOW_UP

    # Page lookup
    if target_page and not identifiers:
        return QueryIntent.PAGE_LOOKUP

    # Summary
    if any(kw in q_lower for kw in _SUMMARY_KEYWORDS):
        return QueryIntent.SUMMARY

    # List/table
    if any(kw in q_lower for kw in _LIST_KEYWORDS):
        return QueryIntent.TABLE_LIST

    # Exact identifier (just the code, nothing else)
    if identifiers:
        # Pure identifier query: "SIH26037" or "26037"
        stripped = re.sub(r'[^a-zA-Z0-9]', '', query)
        for ident in identifiers:
            clean_ident = re.sub(r'[^a-zA-Z0-9]', '', ident)
            if stripped.upper() == clean_ident.upper():
                return QueryIntent.EXACT_IDENTIFIER

        # Identifier + context: "What is SIH26037?", "Tell me about SIH26037"
        if target_fields or any(kw in q_lower for kw in ["what is", "tell me", "give me", "show me", "find", "details"]):
            return QueryIntent.IDENTIFIER_DETAIL

        return QueryIntent.IDENTIFIER_DETAIL

    # Keyword-heavy queries (short, no question words)
    words = q_lower.split()
    if len(words) <= 4 and not any(w in q_lower for w in ["what", "how", "why", "which", "who", "where"]):
        return QueryIntent.KEYWORD

    return QueryIntent.SEMANTIC


def resolve_follow_up(query: str, conversation_history: List[dict]) -> Optional[str]:
    """Attempt to resolve follow-up references using conversation history.

    Returns the resolved query or None if not a follow-up.
    """
    if not conversation_history:
        return None

    # Find the last identifier mentioned in conversation
    last_identifier = None
    for msg in reversed(conversation_history):
        content = msg.get("content", "")
        ids = extract_identifiers(content)
        if ids:
            last_identifier = ids[0]
            break

    if last_identifier:
        # Replace pronouns with the identifier
        q_lower = query.lower()
        replacements = {
            "it": last_identifier,
            "its": f"{last_identifier}'s",
            "this": last_identifier,
            "that": last_identifier,
            "the same": last_identifier,
        }
        resolved = query
        for pronoun, replacement in replacements.items():
            # Replace whole word only
            resolved = re.sub(rf'\b{pronoun}\b', replacement, resolved, flags=re.I)
        return resolved

    return None


def route_query(query: str, conversation_history: Optional[List[dict]] = None) -> QueryPlan:
    """Main entry point: analyze query and produce a QueryPlan."""
    # Normalize
    normalized = query.strip()
    normalized_lower = normalized.lower()

    # Extract components
    identifiers = extract_identifiers(normalized)
    target_page = extract_target_page(normalized)
    target_fields = detect_target_fields(normalized)
    is_follow_up = detect_follow_up(normalized)

    # Resolve follow-ups
    resolved_query = None
    if is_follow_up and conversation_history:
        resolved_query = resolve_follow_up(normalized, conversation_history)
        if resolved_query:
            # Re-extract identifiers from resolved query
            resolved_ids = extract_identifiers(resolved_query)
            if resolved_ids:
                identifiers = resolved_ids

    # Detect comparison IDs
    comparison_ids = []
    if len(identifiers) >= 2 and any(kw in normalized_lower for kw in _COMPARISON_KEYWORDS):
        comparison_ids = identifiers[:2]

    # Classify intent
    intent = classify_intent(
        normalized, identifiers, target_fields, target_page, is_follow_up
    )

    plan = QueryPlan(
        original_query=query,
        normalized_query=normalized,
        identifiers=identifiers,
        intent=intent,
        target_fields=target_fields,
        target_page=target_page,
        is_follow_up=is_follow_up,
        resolved_query=resolved_query,
        comparison_ids=comparison_ids,
    )

    log.info(
        "QueryRouter: intent=%s identifiers=%s fields=%s page=%s follow_up=%s",
        intent.value, identifiers, target_fields, target_page, is_follow_up,
    )
    return plan
