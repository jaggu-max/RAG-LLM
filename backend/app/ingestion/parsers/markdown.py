"""Markdown parser — strips formatting, preserves structure."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.utils.text import clean_text


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    filepath = Path(filepath)
    text = filepath.read_text(encoding="utf-8", errors="replace")

    # Split by headings to preserve section structure
    sections: List[Tuple[str, str]] = []
    current_heading = ""
    current_text = ""

    for line in text.split("\n"):
        if re.match(r"^#{1,6}\s+", line):
            if current_text.strip():
                sections.append((current_heading, current_text))
            current_heading = re.sub(r"^#{1,6}\s+", "", line).strip()
            current_text = line + "\n"
        else:
            current_text += line + "\n"

    if current_text.strip():
        sections.append((current_heading, current_text))

    results = []
    for heading, sec_text in sections:
        cleaned = clean_text(sec_text)
        if cleaned:
            results.append((cleaned, {
                "section": heading,
                "source_type": "markdown",
            }))

    return results
