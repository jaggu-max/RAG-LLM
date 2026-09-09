"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings


# Resolve paths relative to the backend/ directory
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────
    APP_NAME: str = "NEXUS"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
    ]

    # ── Gemini ───────────────────────────────────────
    GEMINI_API_KEY: str = ""

    # ── LM Studio ───────────────────────────────────
    LMSTUDIO_BASE_URL: str = "http://127.0.0.1:1234/v1"
    LMSTUDIO_MODEL: str = "qwen2.5-7b-instruct-1m"

    # ── Memory & Storage Paths ──────────────────────
    CONVERSATION_MEMORY_LIMIT: int = 10
    CHROMA_PATH: str = str(_BACKEND_DIR / "chroma_db")
    CHROMA_COLLECTION: str = "nexus_documents"
    DATASET_PATH: str = str(_BACKEND_DIR / "dataset")
    UPLOAD_PATH: str = str(_BACKEND_DIR / "uploads")
    DB_PATH: str = str(_BACKEND_DIR / "nexus.db")
    CONVERSATIONS_DB_PATH: str = str(_BACKEND_DIR / "data" / "conversations.db")

    # ── Embeddings ──────────────────────────────────
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── RAG ─────────────────────────────────────────
    TOP_K: int = 10
    FINAL_TOP_K: int = 5
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120
    MAX_CONTEXT_CHARS: int = 2000
    CONFIDENCE_THRESHOLD: float = 0.70

    # ── Hybrid Search Weights ───────────────────────
    SEMANTIC_WEIGHT: float = 0.7
    KEYWORD_WEIGHT: float = 0.3

    # ── Feature Flags ───────────────────────────────
    RERANKER_ENABLED: bool = True
    AUTO_INDEX: bool = True
    FALLBACK_ENABLED: bool = True

    # ── File Upload ─────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50

    model_config = {
        "env_file": str(_BACKEND_DIR / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

# Ensure directories exist
for p in (settings.DATASET_PATH, settings.UPLOAD_PATH, settings.CHROMA_PATH, os.path.dirname(settings.CONVERSATIONS_DB_PATH)):
    os.makedirs(p, exist_ok=True)
