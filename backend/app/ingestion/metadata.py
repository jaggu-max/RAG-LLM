"""Metadata extractor — extracts and normalizes document metadata."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.utils.hashing import hash_file

EXTENSION_MAP = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "docx",
    ".txt": "txt", ".md": "markdown",
    ".csv": "csv", ".xlsx": "xlsx", ".xls": "xlsx",
    ".pptx": "pptx",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".json": "json",
    ".rtf": "rtf", ".ods": "ods", ".odt": "odt",
}


def extract_metadata(filepath: str | Path) -> Dict[str, Any]:
    """Build metadata dict for a file."""
    filepath = Path(filepath)
    ext = filepath.suffix.lower()
    file_type = EXTENSION_MAP.get(ext, ext.lstrip("."))

    stat = filepath.stat()

    return {
        "id": uuid.uuid4().hex[:16],
        "filename": filepath.name,
        "file_type": file_type,
        "file_path": str(filepath),
        "size_bytes": stat.st_size,
        "file_hash": hash_file(filepath),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def detect_dataset_type(filepath: str | Path, text: str) -> str:
    """Try to detect if a document is a timetable, marksheet, or general."""
    name = Path(filepath).stem.lower()
    text_lower = text[:2000].lower()

    timetable_keywords = ["monday", "tuesday", "wednesday", "thursday", "friday",
                          "saturday", "time", "period", "lecture", "lab", "slot"]
    marksheet_keywords = ["marks", "total", "grade", "result", "usn", "sgpa", "cgpa",
                          "pass", "fail", "semester", "internal", "external"]
    faculty_keywords = ["faculty", "professor", "department", "designation", "hod",
                        "lecturer", "instructor"]

    if "timetable" in name or sum(1 for k in timetable_keywords if k in text_lower) >= 3:
        return "timetable"
    if "marksheet" in name or "marks" in name or sum(1 for k in marksheet_keywords if k in text_lower) >= 3:
        return "marksheet"
    if "faculty" in name or sum(1 for k in faculty_keywords if k in text_lower) >= 2:
        return "faculty"
    return "general"
