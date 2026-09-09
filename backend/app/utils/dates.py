"""Date utilities — parsing and formatting helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import calendar


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def resolve_day_reference(text: str) -> str | None:
    """Resolve 'today', 'tomorrow', 'next monday' etc. to a weekday name."""
    text = text.lower().strip()
    today = datetime.now()
    day_map = {
        "today": today,
        "tomorrow": today + timedelta(days=1),
        "yesterday": today - timedelta(days=1),
        "day after tomorrow": today + timedelta(days=2),
    }

    if text in day_map:
        return calendar.day_name[day_map[text].weekday()]

    # "next monday", "next friday", etc.
    for i, name in enumerate(calendar.day_name):
        if f"next {name.lower()}" == text:
            days_ahead = i - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target = today + timedelta(days=days_ahead)
            return calendar.day_name[target.weekday()]

    # Check if the text is directly a day name
    for name in calendar.day_name:
        if text == name.lower():
            return name

    return None


def get_current_day_name() -> str:
    return calendar.day_name[datetime.now().weekday()]
