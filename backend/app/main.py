"""Nexus-RAG Backend — FastAPI Application Entry Point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging("DEBUG" if settings.DEBUG else "INFO")
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    # ── Startup ──────────────────────────────────────
    log.info("═" * 50)
    log.info("  NEXUS — Enterprise RAG AI Assistant")
    log.info("═" * 50)

    # 1. Initialize SQLite database
    from app.models.database import init_db
    init_db()
    from app.models.conversation_db import init_conversation_db
    init_conversation_db()

    # 2. Initialize ChromaDB
    from app.models.database import get_chroma_client
    get_chroma_client()

    # 3. Pre-load embedding model (background)
    import threading

    def _preload_embeddings():
        try:
            from app.services.embedding_service import EmbeddingService
            svc = EmbeddingService()
            svc.is_ready()
            log.info("✓ Embedding model ready (dim=%d)", svc.dimension)
        except Exception as e:
            log.warning("Embedding preload deferred: %s", e)

    threading.Thread(target=_preload_embeddings, daemon=True).start()

    # 4. Index existing dataset files
    if settings.AUTO_INDEX:
        def _initial_index():
            try:
                from app.ingestion.processor import index_all_files
                count = index_all_files()
                if count:
                    log.info("✓ Initial indexing: %d documents", count)
            except Exception as e:
                log.warning("Initial indexing deferred: %s", e)

        threading.Thread(target=_initial_index, daemon=True).start()

    # 5. Start file watcher
    from app.ingestion.watcher import start_watcher
    start_watcher()

    log.info("✓ NEXUS backend ready — http://localhost:8000")
    log.info("✓ API docs — http://localhost:8000/docs")

    yield  # ── Application running ──

    # ── Shutdown ─────────────────────────────────────
    from app.ingestion.watcher import stop_watcher
    stop_watcher()
    log.info("NEXUS backend shut down.")


def create_app() -> FastAPI:
    app = FastAPI(
        title="NEXUS — Enterprise RAG API",
        version="1.0.0",
        description="Intelligent Retrieval-Augmented Generation System",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    from app.api.routes_health import router as health_router
    from app.api.routes_chat import router as chat_router
    from app.api.routes_documents import router as documents_router
    from app.api.routes_stats import router as stats_router
    from app.api.routes_models import router as models_router
    from app.api.routes_reindex import router as reindex_router
    from app.api.routes_conversations import router as conversations_router

    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(chat_router, prefix="/api", tags=["Chat"])
    app.include_router(documents_router, prefix="/api", tags=["Documents"])
    app.include_router(stats_router, prefix="/api", tags=["Stats"])
    app.include_router(models_router, prefix="/api", tags=["Models"])
    app.include_router(reindex_router, prefix="/api", tags=["Reindex"])
    app.include_router(conversations_router, prefix="/api", tags=["Conversations"])

    return app


app = create_app()
