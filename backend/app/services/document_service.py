"""Document service — CRUD operations for document management."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import sanitize_filename, validate_file_extension, validate_file_size
from app.ingestion.processor import process_file, reindex_document, remove_file
from app.models.database import (
    delete_document as db_delete,
    get_document,
    list_documents as db_list,
)

log = get_logger(__name__)


def list_documents() -> List[Dict[str, Any]]:
    return db_list()


def get_document_by_id(doc_id: str) -> Optional[Dict[str, Any]]:
    return get_document(doc_id)


async def upload_document(filename: str, content: bytes) -> Dict[str, Any]:
    """Save uploaded file to dataset directory and trigger indexing."""
    # Validate
    safe_name = sanitize_filename(filename)
    if not validate_file_extension(safe_name):
        raise ValueError(f"Unsupported file type: {Path(safe_name).suffix}")
    if not validate_file_size(len(content)):
        raise ValueError(f"File too large. Maximum: {settings.MAX_UPLOAD_SIZE_MB} MB")

    # Save to dataset directory
    dest = Path(settings.DATASET_PATH) / safe_name

    # Handle name collisions
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        counter = 1
        while dest.exists():
            dest = Path(settings.DATASET_PATH) / f"{stem}_{counter}{suffix}"
            counter += 1

    dest.write_bytes(content)
    log.info("Uploaded file saved: %s (%d bytes)", dest.name, len(content))

    # Process immediately
    doc_id = process_file(dest)
    if not doc_id:
        raise RuntimeError(f"Failed to process uploaded file: {safe_name}")

    return {
        "document_id": doc_id,
        "filename": dest.name,
        "message": f"Document '{dest.name}' uploaded and indexed successfully.",
    }


def delete_document_by_id(doc_id: str) -> bool:
    """Delete a document and its data cleanly."""
    doc = get_document(doc_id)
    if not doc:
        log.warning("Delete requested for non-existent document ID: %s", doc_id)
        return False

    file_path_str = doc.get("file_path", "")

    # 1. Remove from ChromaDB & FTS
    if file_path_str:
        try:
            remove_file(file_path_str)
        except Exception as e:
            log.warning("Failed remove_file for %s: %s", file_path_str, e)

    # 2. Delete ChromaDB vector embeddings by document_id directly
    try:
        from app.models.database import delete_from_chroma
        delete_from_chroma(doc_id)
    except Exception as e:
        log.warning("Failed delete_from_chroma for %s: %s", doc_id, e)

    # 3. Delete physical file if present
    if file_path_str:
        fp = Path(file_path_str)
        if fp.exists():
            try:
                fp.unlink()
                log.info("Deleted physical file: %s", fp)
            except Exception as e:
                log.warning("Failed to unlink file %s: %s", fp, e)

    # 4. Delete from SQLite DB
    try:
        db_delete(doc_id)
    except Exception as e:
        log.error("Failed SQLite delete for %s: %s", doc_id, e)

    log.info("Successfully deleted document: %s (id=%s)", doc.get("filename", doc_id), doc_id)
    return True


def trigger_reindex(doc_id: str) -> Optional[str]:
    """Force re-index of a specific document."""
    return reindex_document(doc_id)
