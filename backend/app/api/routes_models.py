"""Models API route — list available LLM models."""

from fastapi import APIRouter

from app.models.schemas import ModelsResponse, ModelInfo
from app.services.lmstudio_service import get_available_models as lmstudio_models

router = APIRouter()


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """Return available local models and their status."""
    models = lmstudio_models()
    return ModelsResponse(
        models=[ModelInfo(**m) for m in models]
    )

