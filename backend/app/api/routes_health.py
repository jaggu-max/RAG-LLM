"""Health-check API route."""

from fastapi import APIRouter

from app.core.config import settings
from app.models.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return service health status for all subsystems."""
    from app.models.database import get_chroma_client
    from app.services.embedding_service import EmbeddingService
    from app.services.gemini_service import health_check as gemini_check
    from app.services.lmstudio_service import health_check as lmstudio_check
    from app.ingestion.watcher import is_watcher_running

    # ChromaDB
    try:
        get_chroma_client()
        chroma_status = "ready"
    except Exception:
        chroma_status = "error"

    # Embeddings
    try:
        embed = EmbeddingService()
        embed_status = "ready" if embed.is_ready() else "error"
    except Exception:
        embed_status = "error"

    # Gemini
    gemini_status = "ready" if gemini_check() else "offline"
    if not settings.GEMINI_API_KEY:
        gemini_status = "not_configured"

    # LM Studio
    lmstudio_status = "ready" if lmstudio_check() else "offline"

    # Watcher
    watcher_status = "running" if is_watcher_running() else "stopped"

    return HealthResponse(
        backend="online",
        chromadb=chroma_status,
        embeddings=embed_status,
        gemini=gemini_status,
        lmstudio=lmstudio_status,
        watcher=watcher_status,
    )
