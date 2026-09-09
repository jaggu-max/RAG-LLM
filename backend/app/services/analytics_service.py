"""Analytics service — query logging and statistics."""

from __future__ import annotations

from typing import Any, Dict

from app.models.database import get_document_stats, get_query_stats


def get_stats() -> Dict[str, Any]:
    """Return combined document + query statistics."""
    doc_stats = get_document_stats()
    query_stats = get_query_stats()

    return {
        "total_documents": doc_stats["total"],
        "indexed_documents": doc_stats["indexed"],
        "pending_documents": doc_stats["pending"],
        "failed_documents": doc_stats["failed"],
        "total_chunks": doc_stats["chunks"],
        "dataset_size_bytes": doc_stats["size"],
        "documents_by_type": doc_stats["by_type"],
        "total_queries": query_stats["total"],
        "avg_response_time_ms": round(query_stats["avg_time"], 1),
        "avg_confidence": round(query_stats["avg_conf"], 4),
    }
