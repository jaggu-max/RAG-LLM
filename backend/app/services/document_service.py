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

    # Process file (parse → chunk → embed → store)
    doc_id = process_file(dest)
    if not doc_id:
        from app.models.database import get_document_by_path
        existing = get_document_by_path(str(dest))
        doc_id = existing["id"] if existing else "unknown"

    return {
        "document_id": doc_id,
        "filename": dest.name,
        "message": f"Document '{dest.name}' uploaded successfully.",
    }


def delete_document_by_id(doc_id: str) -> bool:
    """Delete a document and its data cleanly."""
    doc = get_document(doc_id)

    if doc:
        file_path_str = doc.get("file_path", "")

        # 1. Remove from ChromaDB & FTS
        if file_path_str:
            try:
                remove_file(file_path_str)
            except Exception as e:
                log.warning("Failed remove_file for %s: %s", file_path_str, e)

        # 2. Delete physical file if present
        if file_path_str:
            fp = Path(file_path_str)
            if fp.exists():
                try:
                    fp.unlink()
                    log.info("Deleted physical file: %s", fp)
                except Exception as e:
                    log.warning("Failed to unlink file %s: %s", fp, e)

    # 3. Delete ChromaDB vector embeddings by document_id directly
    try:
        from app.models.database import delete_from_chroma
        delete_from_chroma(doc_id)
    except Exception as e:
        log.warning("Failed delete_from_chroma for %s: %s", doc_id, e)

    # 4. Delete from SQLite DB
    try:
        db_delete(doc_id)
    except Exception as e:
        log.error("Failed SQLite delete for %s: %s", doc_id, e)

    log.info("Successfully deleted document ID: %s", doc_id)
    return True


def trigger_reindex(doc_id: str) -> Optional[str]:
    """Force re-index of a specific document."""
    return reindex_document(doc_id)


def reprocess_ocr_document(doc_id: str) -> Optional[str]:
    """Reprocess OCR for an image document by purging old chunks and running fresh OCR."""
    doc = get_document(doc_id)
    if not doc:
        return None

    from app.ingestion.processor import resolve_document_file_path, process_file
    resolved_path = resolve_document_file_path(doc.get("file_path", ""))
    if not resolved_path.exists():
        resolved_path = resolve_document_file_path(doc.get("filename", ""))
        if not resolved_path.exists():
            log.error("Reprocess OCR failed: Physical file missing for %s (%s)", doc_id, doc.get("filename"))
            return None

    log.info("Reprocessing OCR for document %s (%s) at %s...", doc_id, doc.get("filename"), resolved_path)
    return process_file(resolved_path, force=True)


def purge_and_reprocess_placeholder_images() -> int:
    """Scan database for image documents containing placeholder chunks and force re-index."""
    reprocessed_count = 0
    try:
        docs = db_list()
        for doc in docs:
            file_type = str(doc.get("file_type", "")).lower()
            if file_type in ("image", "png", "jpg", "jpeg", "webp"):
                doc_id = doc["id"]
                # Check if FTS chunks contain forbidden placeholders
                from app.models.database import get_document_chunks
                chunks = get_document_chunks(doc_id)
                has_placeholder = False
                if not chunks:
                    has_placeholder = True
                else:
                    for c in chunks:
                        txt_lower = str(c.get("text", "")).lower()
                        if "ocr processing complete" in txt_lower or "[image:" in txt_lower or "visual content" in txt_lower:
                            has_placeholder = True
                            break

                if has_placeholder:
                    log.info("Found broken placeholder chunks for image %s (%s). Reprocessing...", doc_id, doc.get("filename"))
                    res = reprocess_ocr_document(doc_id)
                    if res:
                        reprocessed_count += 1
    except Exception as e:
        log.error("Failed purging placeholder images: %s", e)
    return reprocessed_count

