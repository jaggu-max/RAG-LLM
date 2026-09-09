"""Document processor — orchestrates parse → chunk → embed → store."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion.chunker import chunk_text
from app.ingestion.metadata import detect_dataset_type, extract_metadata
from app.models.database import (
    add_to_chroma, delete_fts_by_document, delete_from_chroma,
    get_document_by_path, insert_document, insert_fts_chunks,
    update_document,
)
from app.utils.hashing import hash_file

log = get_logger(__name__)

# Parser registry
PARSER_MAP = {
    "pdf": "app.ingestion.parsers.pdf",
    "docx": "app.ingestion.parsers.docx",
    "txt": "app.ingestion.parsers.txt",
    "markdown": "app.ingestion.parsers.markdown",
    "csv": "app.ingestion.parsers.csv",
    "xlsx": "app.ingestion.parsers.xlsx",
    "pptx": "app.ingestion.parsers.pptx",
    "image": "app.ingestion.parsers.images",
    "json": "app.ingestion.parsers.json",
    "rtf": "app.ingestion.parsers.office",
    "ods": "app.ingestion.parsers.office",
    "odt": "app.ingestion.parsers.office",
}

EXTENSION_TO_TYPE = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "docx",
    ".txt": "txt", ".md": "markdown",
    ".csv": "csv", ".xlsx": "xlsx", ".xls": "xlsx",
    ".pptx": "pptx",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".json": "json",
    ".rtf": "rtf", ".ods": "ods", ".odt": "odt",
}

# Lazy-loaded embedding service
_embed_service = None


def _get_embed_service():
    global _embed_service
    if _embed_service is None:
        from app.services.embedding_service import EmbeddingService
        _embed_service = EmbeddingService()
    return _embed_service


def process_file(filepath: str | Path, force: bool = False) -> Optional[str]:
    """Process a single file: parse → chunk → embed → store.

    Returns the document_id on success, or None on failure.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        log.warning("File not found: %s", filepath)
        return None

    ext = filepath.suffix.lower()
    file_type = EXTENSION_TO_TYPE.get(ext)
    if not file_type:
        log.warning("Unsupported file type: %s", ext)
        return None

    # Check if already indexed with same hash
    file_hash = hash_file(filepath)
    existing = get_document_by_path(str(filepath))

    if existing and existing["file_hash"] == file_hash and not force:
        log.info("File unchanged (hash match): %s", filepath.name)
        return existing["id"]

    # If exists but hash changed, remove old data
    if existing:
        log.info("File changed, re-indexing: %s", filepath.name)
        _remove_document_data(existing["id"])
        doc_id = existing["id"]
    else:
        meta = extract_metadata(filepath)
        doc_id = meta["id"]

    # Create/update document record
    doc_record = {
        "id": doc_id,
        "filename": filepath.name,
        "file_type": file_type,
        "file_path": str(filepath),
        "size_bytes": filepath.stat().st_size,
        "file_hash": file_hash,
        "status": "processing",
        "created_at": existing["created_at"] if existing else None,
    }
    if not doc_record["created_at"]:
        from app.utils.dates import now_iso
        doc_record["created_at"] = now_iso()
    insert_document(doc_record)

    try:
        # 1. Parse
        parser_module = PARSER_MAP.get(file_type)
        if not parser_module:
            raise ValueError(f"No parser for type: {file_type}")

        import importlib
        parser = importlib.import_module(parser_module)
        parsed_sections = parser.parse(filepath)

        if not parsed_sections:
            update_document(doc_id, status="failed", error_message="No readable content found")
            log.warning("No content extracted from: %s", filepath.name)
            return None

        # 2. Detect dataset type
        all_text = "\n\n".join(text for text, _ in parsed_sections)
        dataset_type = detect_dataset_type(filepath, all_text)

        # 3. Chunk
        all_chunks = []
        for section_text, section_meta in parsed_sections:
            chunk_meta = {
                "file_name": filepath.name,
                "file_type": file_type,
                "file_path": str(filepath),
                "dataset_type": dataset_type,
                **section_meta,
            }
            chunks = chunk_text(section_text, chunk_meta, doc_id)
            all_chunks.extend(chunks)

        if not all_chunks:
            update_document(doc_id, status="failed", error_message="Chunking produced no results")
            return None

        # 4. Embed
        embed_service = _get_embed_service()
        texts = [c["text"] for c in all_chunks]
        embeddings = embed_service.embed_batch(texts)

        # 5. Store in ChromaDB
        ids = [c["chunk_id"] for c in all_chunks]
        metadatas = [c["metadata"] for c in all_chunks]
        add_to_chroma(ids, embeddings, texts, metadatas)

        # 6. Store in FTS5 for keyword search
        insert_fts_chunks(all_chunks)

        # 7. Update document record
        update_document(
            doc_id,
            status="indexed",
            chunks=len(all_chunks),
            dataset_type=dataset_type,
            indexed_at=__import__("app.utils.dates", fromlist=["now_iso"]).now_iso(),
        )

        log.info("✓ Indexed: %s → %d chunks [%s]", filepath.name, len(all_chunks), dataset_type)
        return doc_id

    except Exception as e:
        log.error("Processing failed for %s: %s", filepath.name, e)
        log.debug(traceback.format_exc())
        update_document(doc_id, status="failed", error_message=str(e)[:500])
        return None


def remove_file(filepath: str | Path) -> None:
    """Remove all data associated with a file."""
    filepath = str(filepath)
    existing = get_document_by_path(filepath)
    if existing:
        _remove_document_data(existing["id"])
        from app.models.database import delete_document
        delete_document(existing["id"])
        log.info("✓ Removed: %s", Path(filepath).name)


def _remove_document_data(doc_id: str) -> None:
    """Remove chunks from ChromaDB and FTS5."""
    delete_from_chroma(doc_id)
    delete_fts_by_document(doc_id)


def reindex_document(doc_id: str) -> Optional[str]:
    """Force re-index of a document by its ID."""
    from app.models.database import get_document
    doc = get_document(doc_id)
    if not doc:
        return None
    filepath = doc["file_path"]
    if not Path(filepath).exists():
        return None
    return process_file(filepath, force=True)


def index_all_files() -> int:
    """Index all files in the dataset directory."""
    dataset_dir = Path(settings.DATASET_PATH)
    if not dataset_dir.exists():
        return 0

    count = 0
    for fp in dataset_dir.iterdir():
        if fp.is_file() and not fp.name.startswith("."):
            ext = fp.suffix.lower()
            if ext in EXTENSION_TO_TYPE:
                result = process_file(fp)
                if result:
                    count += 1
    return count
