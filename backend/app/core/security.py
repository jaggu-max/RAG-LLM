"""Security utilities — file validation, sanitization, CORS."""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from app.core.config import settings

ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".xls",
    ".pptx", ".json", ".png", ".jpg", ".jpeg", ".rtf", ".ods", ".odt",
}

MAX_UPLOAD_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def sanitize_filename(filename: str) -> str:
    """Strip dangerous characters and normalize Unicode."""
    filename = unicodedata.normalize("NFKD", filename)
    filename = os.path.basename(filename)  # remove any path component
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    filename = filename.strip(". ")
    if not filename:
        filename = "unnamed_file"
    return filename


def validate_file_extension(filename: str) -> bool:
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS


def validate_file_size(size_bytes: int) -> bool:
    return 0 < size_bytes <= MAX_UPLOAD_BYTES


def prevent_path_traversal(filepath: str, base_dir: str) -> bool:
    """Ensure resolved path is within the base directory."""
    resolved = os.path.realpath(filepath)
    base = os.path.realpath(base_dir)
    return resolved.startswith(base)
