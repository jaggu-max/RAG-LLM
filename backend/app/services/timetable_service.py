"""Timetable service — structured timetable parsing and date-aware queries."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.utils.dates import get_current_day_name, resolve_day_reference

log = get_logger(__name__)


def detect_timetable_query(query: str) -> Optional[Dict[str, Any]]:
    """Detect if a query is timetable-related and extract parameters."""
    query_lower = query.lower()

    timetable_patterns = [
        r"what class.*(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"what.*schedule.*(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"class.*(today|tomorrow|next)",
        r"lecture.*(today|tomorrow|next)",
        r"lab.*(today|tomorrow|next|monday|tuesday|wednesday|thursday|friday|saturday)",
        r"who teaches\s+(\w+)",
        r"which (room|lab|class).*(on|at|for)",
        r"what (is|are).*(at|on)\s+\d",
        r"timetable.*for\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
        r"schedule.*for\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
    ]

    is_timetable = any(re.search(p, query_lower) for p in timetable_patterns)
    if not is_timetable:
        return None

    # Extract day reference
    day = None
    day_words = ["today", "tomorrow", "yesterday", "day after tomorrow"]
    for dw in day_words:
        if dw in query_lower:
            day = resolve_day_reference(dw)
            break

    if not day:
        for match in re.finditer(r"(next\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
                                  query_lower):
            full_match = match.group(0)
            day = resolve_day_reference(full_match)
            break

    # Extract time reference
    time_match = re.search(r'(\d{1,2}[:.]\d{2})', query_lower)
    time_ref = time_match.group(1) if time_match else None

    # Extract subject
    subject = None
    who_teaches = re.search(r"who teaches\s+(.+?)(\?|$)", query_lower)
    if who_teaches:
        subject = who_teaches.group(1).strip().upper()

    return {
        "is_timetable": True,
        "day": day,
        "time": time_ref,
        "subject": subject,
        "current_day": get_current_day_name(),
    }


def format_timetable_context(query: str, timetable_info: Dict[str, Any]) -> str:
    """Add timetable context to the query for better retrieval."""
    parts = [query]

    if timetable_info.get("day"):
        parts.append(f"\n[System context: The user is asking about {timetable_info['day']}. "
                    f"Today is {timetable_info['current_day']}.]")

    if timetable_info.get("time"):
        parts.append(f"[Time reference: {timetable_info['time']}]")

    if timetable_info.get("subject"):
        parts.append(f"[Subject: {timetable_info['subject']}]")

    return " ".join(parts)
