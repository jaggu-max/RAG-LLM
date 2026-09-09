"""XLSX parser — reads Excel spreadsheets sheet-by-sheet."""

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
        xls = pd.ExcelFile(str(filepath), engine="openpyxl")
    except Exception as e:
        log.error("XLSX parse error for %s: %s", filepath.name, e)
        raise

    for sheet_name in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name)
        except Exception as e:
            log.warning("Cannot read sheet '%s': %s", sheet_name, e)
            continue

        if df.empty:
            continue

        columns = list(df.columns)
        row_texts: List[str] = []

        for _, row in df.iterrows():
            parts = []
            for col in columns:
                val = row.get(col, "")
                if pd.notna(val) and str(val).strip():
                    parts.append(f"{col}: {str(val).strip()}")
            if parts:
                row_texts.append("\n".join(parts))

        # Group rows
        chunk_size = 20
        for i in range(0, len(row_texts), chunk_size):
            batch = row_texts[i : i + chunk_size]
            text = "\n\n".join(batch)
            cleaned = clean_text(text)
            if cleaned:
                results.append((cleaned, {
                    "source_type": "xlsx",
                    "sheet_name": sheet_name,
                    "columns": ", ".join(columns),
                    "row_range": f"{i+1}-{min(i+chunk_size, len(row_texts))}",
                }))

    log.info("XLSX parsed: %s → %d chunks", filepath.name, len(results))
    return results
