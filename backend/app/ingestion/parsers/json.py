"""JSON parser — flattens JSON into searchable key-value text."""

from __future__ import annotations

import json as json_lib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.utils.text import clean_text


def _flatten(obj: Any, prefix: str = "") -> List[str]:
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            lines.extend(_flatten(v, key))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            lines.extend(_flatten(item, f"{prefix}[{i}]"))
    else:
        lines.append(f"{prefix}: {obj}")
    return lines


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    filepath = Path(filepath)

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json_lib.load(f)
    except Exception:
        with open(filepath, "r", encoding="latin-1") as f:
            data = json_lib.load(f)

    lines = _flatten(data)
    text = "\n".join(lines)
    cleaned = clean_text(text)

    if not cleaned:
        return []

    # Split into chunks if very large
    chunk_size = 3000  # chars
    results = []
    for i in range(0, len(cleaned), chunk_size):
        chunk = cleaned[i : i + chunk_size]
        results.append((chunk, {"source_type": "json"}))

    return results
