"""PDF parser — extracts text page-by-page using PyMuPDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.core.logging import get_logger
from app.utils.text import clean_text

log = get_logger(__name__)


def parse(filepath: str | Path) -> List[Tuple[str, Dict[str, Any]]]:
    """Return list of (text, metadata) tuples, one per page."""
    filepath = Path(filepath)
    results: List[Tuple[str, Dict[str, Any]]] = []

    # Primary: PyMuPDF (fitz)
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(filepath))
        total_pages = len(doc)

        for page_num in range(total_pages):
            page = doc[page_num]

            # Extract text and strip NUL bytes
            raw_text = page.get_text("text").replace("\x00", "")

            # For large PDFs (>30 pages), skip slow grid find_tables if text is abundant
            table_text = ""
            if total_pages <= 30 or len(raw_text.strip()) < 100:
                try:
                    tables = page.find_tables()
                    if tables and tables.tables:
                        for table in tables.tables:
                            try:
                                for row in table.extract():
                                    cells = [str(c).strip().replace("\x00", "") if c else "" for c in row]
                                    if any(cells):
                                        table_text += " | ".join(cells) + "\n"
                                table_text += "\n"
                            except Exception:
                                pass
                except Exception:
                    pass

            combined = clean_text(raw_text)
            if table_text.strip():
                combined += "\n\n[TABLE]\n" + clean_text(table_text)

            if combined.strip():
                results.append((combined, {
                    "page_number": page_num + 1,
                    "source_type": "pdf",
                }))
        doc.close()
    except Exception as e:
        log.warning("PyMuPDF failed for %s, trying pypdf fallback: %s", filepath.name, e)
        results = []

    # Fallback: pypdf if PyMuPDF produced no results or failed
    if not results:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(filepath))
            for page_num, page in enumerate(reader.pages):
                text = (page.extract_text() or "").replace("\x00", "")
                cleaned = clean_text(text)
                if cleaned.strip():
                    results.append((cleaned, {
                        "page_number": page_num + 1,
                        "source_type": "pdf",
                    }))
            log.info("pypdf extracted %d pages from %s", len(results), filepath.name)
        except Exception as fallback_err:
            log.error("pypdf fallback failed for %s: %s", filepath.name, fallback_err)

    # Scanned PDF Fallback: if 0 text extracted, use PyMuPDF 150 DPI rendering + OpenCV preprocessing + EasyOCR
    if not results:
        try:
            import pymupdf as fitz
            import cv2
            import easyocr
            import numpy as np

            reader = easyocr.Reader(["en"], gpu=False)
            doc = fitz.open(str(filepath))
            total_pages = len(doc)
            log.info("Running PyMuPDF 150 DPI + OpenCV + EasyOCR on %d scanned pages: %s", total_pages, filepath.name)

            for page_num in range(total_pages):
                page = doc[page_num]
                pix = page.get_pixmap(dpi=150)
                img_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))

                # OpenCV Preprocessing to improve OCR accuracy
                if pix.n >= 3:
                    gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
                else:
                    gray = img_np
                denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

                text_list = reader.readtext(denoised, detail=0)
                extracted_text = " ".join(text_list).strip().replace("\x00", "")

                page_label = f"[Scanned PDF Page {page_num + 1} of {total_pages} — {filepath.name}]\n"
                full_text = page_label + (extracted_text if extracted_text else "Visual page content.")

                results.append((
                    full_text,
                    {
                        "page_number": page_num + 1,
                        "total_pages": total_pages,
                        "source_type": "pdf_scanned",
                        "file_name": filepath.name,
                    }
                ))
            doc.close()
            log.info("✓ OpenCV + EasyOCR finished for %d pages: %s", total_pages, filepath.name)
        except Exception as scan_err:
            log.error("Scanned PDF OCR fallback failed for %s: %s", filepath.name, scan_err)
            try:
                import fitz
                doc = fitz.open(str(filepath))
                total_pages = len(doc)
                for page_num in range(total_pages):
                    results.append((
                        f"[Scanned PDF Page {page_num + 1} of {total_pages} — {filepath.name}]\nVisual page from scanned document {filepath.name}.",
                        {
                            "page_number": page_num + 1,
                            "total_pages": total_pages,
                            "source_type": "pdf_scanned",
                            "file_name": filepath.name,
                        }
                    ))
                doc.close()
            except Exception:
                pass

    log.info("PDF parsed: %s → %d pages", filepath.name, len(results))
    return results


def extract_structured_records_from_pages(
    pages: List[Tuple[str, Dict[str, Any]]],
    file_name: str,
    doc_id: str,
) -> List[Dict[str, Any]]:
    """Extract structured SIH problem statement records from parsed PDF pages."""
    import re

    records = []
    # Match SIH problem codes
    sih_re = re.compile(r'\b(SIH\s*[-_]?\s*\d{4,6})\b', re.I)

    for text, meta in pages:
        page_num = meta.get("page_number", 0)

        # Find all SIH codes on this page
        matches = list(sih_re.finditer(text))
        if not matches:
            continue

        for i, match in enumerate(matches):
            raw_code = match.group(1)
            clean_code = "SIH" + re.sub(r'\D', '', raw_code)

            # Extract block around this match up to the next match or page end
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            block = text[start_pos:end_pos].strip()

            # Parse fields from block
            record = {
                "id": f"{doc_id}_{clean_code}_{page_num}",
                "document_id": doc_id,
                "record_type": "sih_problem_statement",
                "identifier": clean_code,
                "ps_code": clean_code,
                "track": _extract_field(block, ["track", "category", "domain"]),
                "problem_statement_title": _extract_field(block, ["title", "problem title", "statement title", "name"]),
                "theme": _extract_field(block, ["theme", "sub-theme", "area"]),
                "sponsoring_ministry": _extract_field(block, ["sponsoring ministry", "organization", "sponsor", "ministry", "funded by"]),
                "problem_statement": _extract_problem_text(block),
                "page_number": page_num,
                "source_document": file_name,
                "raw_text": block[:1500],
            }
            records.append(record)

    log.info("Extracted %d structured records from %s", len(records), file_name)
    return records


def _extract_field(text: str, field_names: List[str]) -> str:
    import re
    for name in field_names:
        # Match "Field Name: Value" or "Field Name | Value"
        pattern = re.compile(rf'\b{re.escape(name)}\s*[:|]\s*(.+?)(?=\n|\||\b(?:Track|Theme|Title|Sponsor|Ministry|PS Code|Category|Description|Problem Statement)[:|]|$)', re.I | re.DOTALL)
        m = pattern.search(text)
        if m:
            val = m.group(1).strip()
            # Clean up trailing pipes/newlines
            val = val.split("|")[0].split("\n")[0].strip()
            if val:
                return val
    return ""


def _extract_problem_text(block: str) -> str:
    import re
    # Match "Problem Statement: ..." or everything after header fields
    pattern = re.compile(r'\b(?:problem statement|description|details)\s*[:|]\s*(.+)', re.I | re.DOTALL)
    m = pattern.search(block)
    if m:
        return m.group(1).strip()
    return block[:1000]

