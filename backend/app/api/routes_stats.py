"""Stats API route."""

from fastapi import APIRouter

from app.models.schemas import DocsByType, StatsResponse
from app.services.analytics_service import get_stats

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def stats():
    """Return system analytics and document statistics."""
    data = get_stats()
    return StatsResponse(
        total_documents=data["total_documents"],
        indexed_documents=data["indexed_documents"],
        pending_documents=data["pending_documents"],
        failed_documents=data["failed_documents"],
        total_chunks=data["total_chunks"],
        dataset_size_bytes=data["dataset_size_bytes"],
        total_queries=data["total_queries"],
        avg_response_time_ms=data["avg_response_time_ms"],
        avg_confidence=data["avg_confidence"],
        documents_by_type=[
            DocsByType(file_type=d["file_type"], count=d["count"])
            for d in data["documents_by_type"]
        ],
    )
