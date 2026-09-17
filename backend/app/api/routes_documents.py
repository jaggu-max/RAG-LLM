"""Document management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional

from app.models.schemas import DocumentListResponse, DocumentResponse, DocumentStatus, DocumentUploadResponse
from app.services.document_service import (
    delete_document_by_id,
    get_document_by_id,
    list_documents,
    trigger_reindex,
    upload_document,
)

router = APIRouter()


@router.get("/documents")
async def get_documents():
    """List all documents."""
    docs = list_documents()
    items = []
    for d in docs:
        items.append(DocumentResponse(
            id=d["id"],
            filename=d["filename"],
            file_type=d["file_type"],
            size_bytes=d.get("size_bytes", 0),
            chunks=d.get("chunks", 0),
            status=DocumentStatus(d.get("status", "pending")),
            indexed_at=d.get("indexed_at"),
            updated_at=d.get("updated_at"),
            file_hash=d.get("file_hash", ""),
        ))
    return DocumentListResponse(documents=items, total=len(items))


@router.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get a single document's details."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(
        id=doc["id"],
        filename=doc["filename"],
        file_type=doc["file_type"],
        size_bytes=doc.get("size_bytes", 0),
        chunks=doc.get("chunks", 0),
        status=DocumentStatus(doc.get("status", "pending")),
        indexed_at=doc.get("indexed_at"),
        updated_at=doc.get("updated_at"),
        file_hash=doc.get("file_hash", ""),
    )


@router.get("/documents/{doc_id}/content")
async def get_document_content(doc_id: str):
    """Get document details along with indexed text chunks for the viewer modal."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.models.database import get_document_chunks
    chunks = get_document_chunks(doc_id)
    actual_chunks_count = len(chunks) if chunks else doc.get("chunks", 0)
    full_text = "\n\n--- CHUNK BREAK ---\n\n".join(c["text"] for c in chunks) if chunks else "No text extracted yet."

    return {
        "id": doc["id"],
        "filename": doc["filename"],
        "file_type": doc["file_type"],
        "size_bytes": doc.get("size_bytes", 0),
        "chunks_count": actual_chunks_count,
        "status": doc.get("status", "pending"),
        "full_text": full_text,
        "chunks": chunks,
        "file_path": doc.get("file_path", ""),
    }


@router.get("/documents/{doc_id}/file")
async def serve_document_file(doc_id: str):
    """Serve the raw uploaded document file (PDF, TXT, DOCX, etc.) for direct browser view."""
    doc = get_document_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from pathlib import Path
    from fastapi.responses import FileResponse

    file_path = Path(doc["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing on server")

    media_type = "application/pdf" if doc["file_type"] == "pdf" else None
    headers = {"Content-Disposition": f"inline; filename=\"{doc['filename']}\""}
    return FileResponse(path=str(file_path), media_type=media_type, headers=headers)


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload(file: UploadFile = File(...)):
    """Upload a document for ingestion."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = await upload_document(file.filename, content)
        return DocumentUploadResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and its indexed data."""
    success = delete_document_by_id(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document deleted successfully"}


@router.post("/documents/{doc_id}/reindex")
async def reindex_document(doc_id: str):
    """Force re-index of a specific document."""
    result = trigger_reindex(doc_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found or file missing")
    return {"message": "Document re-indexed successfully", "document_id": result}
