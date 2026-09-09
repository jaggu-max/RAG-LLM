"""PDF parser — extracts text page-by-page using PyMuPDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.logging import get_logger
from app.utils.text import clean_text

log = get_logger(__name__)


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    """Return list of (text, metadata) tuples, one per page."""
    import fitz  # PyMuPDF

    filepath = Path(filepath)
    results: List[Tuple[str, Dict[str, Any]]] = []

    try:
        doc = fitz.open(str(filepath))
        for page_num in range(len(doc)):
            page = doc[page_num]

            # Extract text
            text = page.get_text("text")

            # Also try to extract tables as structured text
            tables = page.find_tables()
            table_text = ""
            if tables and tables.tables:
                for table in tables.tables:
                    try:
                        for row in table.extract():
                            cells = [str(c).strip() if c else "" for c in row]
                            if any(cells):
                                table_text += " | ".join(cells) + "\n"
                        table_text += "\n"
                    except Exception:
                        pass

            combined = clean_text(text)
            if table_text.strip():
                combined += "\n\n[TABLE]\n" + clean_text(table_text)

            if combined.strip():
                results.append((combined, {
                    "page_number": page_num + 1,
                    "source_type": "pdf",
                }))
        doc.close()
    except Exception as e:
        log.error("PDF parse error for %s: %s", filepath.name, e)
        raise

    if not results:
        # Try plain text extraction as fallback
        try:
            doc = fitz.open(str(filepath))
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            doc.close()
            if full_text.strip():
                results.append((clean_text(full_text), {"page_number": 1, "source_type": "pdf"}))
        except Exception:
            pass

    log.info("PDF parsed: %s → %d pages", filepath.name, len(results))
    return results
