"""CSV parser — reads tabular data row-by-row into searchable text."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from app.core.logging import get_logger
from app.utils.text import clean_text

log = get_logger(__name__)


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    filepath = Path(filepath)
    results: List[Tuple[str, Dict[str, Any]]] = []

    try:
        df = pd.read_csv(str(filepath), encoding="utf-8", on_bad_lines="skip")
    except UnicodeDecodeError:
        df = pd.read_csv(str(filepath), encoding="latin-1", on_bad_lines="skip")
    except Exception as e:
        log.error("CSV parse error for %s: %s", filepath.name, e)
        raise

    if df.empty:
        return []

    columns = list(df.columns)

    # Build structured text per row
    row_texts: List[str] = []
    for idx, row in df.iterrows():
        parts = []
        for col in columns:
            val = row.get(col, "")
            if pd.notna(val) and str(val).strip():
                parts.append(f"{col}: {str(val).strip()}")
        if parts:
            row_texts.append("\n".join(parts))

    # Group rows into chunks of ~20 rows for efficiency
    chunk_size = 20
    for i in range(0, len(row_texts), chunk_size):
        batch = row_texts[i : i + chunk_size]
        text = "\n\n".join(batch)
        cleaned = clean_text(text)
        if cleaned:
            results.append((cleaned, {
                "source_type": "csv",
                "columns": ", ".join(columns),
                "row_range": f"{i+1}-{min(i+chunk_size, len(row_texts))}",
            }))

    log.info("CSV parsed: %s → %d chunks (%d rows)", filepath.name, len(results), len(row_texts))
    return results
