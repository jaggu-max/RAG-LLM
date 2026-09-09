"""Embedding service — local Sentence Transformers embeddings."""

from __future__ import annotations

from typing import List

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class EmbeddingService:
    """Wraps sentence-transformers for local embedding generation."""

    _instance = None
    _model = None

    def __new__(cls) -> "EmbeddingService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_model(self):
        if self._model is None:
            log.info("Loading embedding model: %s", settings.EMBEDDING_MODEL)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
            log.info("✓ Embedding model loaded")

    def embed(self, text: str) -> List[float]:
        """Embed a single text string."""
        self._load_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """Embed a batch of texts."""
        self._load_model()
        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def is_ready(self) -> bool:
        try:
            self._load_model()
            return True
        except Exception as e:
            log.error("Embedding model not ready: %s", e)
            return False

    @property
    def dimension(self) -> int:
        self._load_model()
        return self._model.get_sentence_embedding_dimension()
