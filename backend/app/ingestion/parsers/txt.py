"""Plain-text parser."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.utils.text import clean_text


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    filepath = Path(filepath)
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    text = ""
    for enc in encodings:
        try:
            text = filepath.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, ValueError):
            continue

    cleaned = clean_text(text)
    if not cleaned:
        return []
    return [(cleaned, {"source_type": "txt"})]
