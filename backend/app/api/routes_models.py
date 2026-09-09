"""Models API route — list available LLM models and manage Gemini key configuration."""

from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.config import settings
from app.models.schemas import ModelsResponse, ModelInfo
from app.services.gemini_provider import gemini_provider
from app.services.gemini_service import get_available_models as gemini_models
from app.services.lmstudio_service import get_available_models as lmstudio_models

router = APIRouter()


class TestKeyRequest(BaseModel):
    api_key: Optional[str] = None


class SaveKeyRequest(BaseModel):
    api_key: str


@router.get("/models", response_model=ModelsResponse)
async def list_models():
    """Return available models and their status."""
    models = gemini_models() + lmstudio_models()
    return ModelsResponse(
        models=[ModelInfo(**m) for m in models]
    )


@router.post("/models/test-gemini-key")
async def test_gemini_key(req: TestKeyRequest):
    """Test Gemini API key connection and return status."""
    status, message = gemini_provider.test_connection(req.api_key)
    return {
        "status": status,
        "message": message,
        "valid": status == "Ready"
    }


@router.post("/models/save-gemini-key")
async def save_gemini_key(req: SaveKeyRequest):
    """Save updated Gemini API key to settings and .env."""
    key = req.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")

    status, message = gemini_provider.test_connection(key)
    if status == "Invalid API Key":
        raise HTTPException(status_code=400, detail="Invalid Gemini API key. Please check your API key.")

    # Update in-memory settings & reset provider cache
    settings.GEMINI_API_KEY = key
    gemini_provider._cached_model_name = None
    gemini_provider._cache_timestamp = 0.0

    # Save to backend/.env
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            lines = content.splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("GEMINI_API_KEY="):
                    new_lines.append(f"GEMINI_API_KEY={key}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"GEMINI_API_KEY={key}")
            env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as e:
        pass

    return {
        "status": status,
        "message": message,
        "valid": status == "Ready"
    }

