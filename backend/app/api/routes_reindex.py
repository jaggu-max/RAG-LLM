"""Reindex API route — trigger full re-ingestion."""

from fastapi import APIRouter

from app.core.logging import get_logger
from app.ingestion.processor import index_all_files

log = get_logger(__name__)

router = APIRouter()


@router.post("/reindex")
async def reindex():
    """Trigger a full reindex of all documents in the dataset directory."""
    log.info("Full reindex triggered via API")
    count = index_all_files()
    return {
        "message": f"Reindex complete. {count} documents processed.",
        "documents_processed": count,
    }
