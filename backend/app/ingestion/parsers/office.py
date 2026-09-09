"""Office parser — ODS, ODT, RTF support."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.logging import get_logger
from app.utils.text import clean_text

log = get_logger(__name__)


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    filepath = Path(filepath)
    ext = filepath.suffix.lower()

    try:
        if ext == ".rtf":
            return _parse_rtf(filepath)
        elif ext == ".ods":
            return _parse_ods(filepath)
        elif ext == ".odt":
            return _parse_odt(filepath)
        else:
            log.warning("Unsupported office format: %s", ext)
            return []
    except Exception as e:
        log.error("Office parse error for %s: %s", filepath.name, e)
        raise


def _parse_rtf(filepath: Path) -> List[Tuple[str, Dict[str, Any]]]:
    from striprtf.striprtf import rtf_to_text
    raw = filepath.read_text(encoding="utf-8", errors="replace")
    text = rtf_to_text(raw)
    cleaned = clean_text(text)
    return [(cleaned, {"source_type": "rtf"})] if cleaned else []


def _parse_ods(filepath: Path) -> List[Tuple[str, Dict[str, Any]]]:
    import pandas as pd
    results = []
    xls = pd.ExcelFile(str(filepath), engine="odf")
    for sheet in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet)
        if df.empty:
            continue
        row_texts = []
        for _, row in df.iterrows():
            parts = [f"{col}: {val}" for col, val in row.items()
                     if pd.notna(val) and str(val).strip()]
            if parts:
                row_texts.append("\n".join(parts))
        if row_texts:
            text = "\n\n".join(row_texts)
            results.append((clean_text(text), {
                "source_type": "ods", "sheet_name": sheet
            }))
    return results


def _parse_odt(filepath: Path) -> List[Tuple[str, Dict[str, Any]]]:
    from odf.opendocument import load as odf_load
    from odf.text import P
    doc = odf_load(str(filepath))
    paragraphs = doc.getElementsByType(P)
    texts = []
    for p in paragraphs:
        t = ""
        for node in p.childNodes:
            if hasattr(node, "data"):
                t += node.data
            elif hasattr(node, "__str__"):
                t += str(node)
        if t.strip():
            texts.append(t.strip())
    text = "\n".join(texts)
    cleaned = clean_text(text)
    return [(cleaned, {"source_type": "odt"})] if cleaned else []
