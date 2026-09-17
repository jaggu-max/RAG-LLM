"""Pydantic models for API request / response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ────────────────────────────────────────────────

class AnswerType(str, Enum):
    DATASET = "dataset"
    GENERAL_KNOWLEDGE = "general_knowledge"
    INSUFFICIENT = "insufficient"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


# ── Chat ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    model: str = Field(default="local_qwen")
    conversation_id: Optional[str] = None
    use_knowledge_base: bool = True



class Source(BaseModel):
    file_name: str
    document_id: Optional[str] = None
    file_type: Optional[str] = None
    page: Optional[int] = None
    pages: List[int] = []
    slide_number: Optional[int] = None
    slides: List[int] = []
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    chunk_count: int = 1
    score: float = 0.0
    sheet_name: Optional[str] = None


class RetrievalInfo(BaseModel):
    semantic_results: int = 0
    keyword_results: int = 0
    reranked_results: int = 0
    unique_source_count: int = 0


class ChatResponse(BaseModel):
    answer: str
    answer_type: AnswerType
    confidence: float
    model: str
    sources: List[Source] = []
    retrieval: RetrievalInfo = RetrievalInfo()
    response_time_ms: int = 0
    conversation_id: Optional[str] = None


# ── Documents ────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    chunks: int = 0
    status: DocumentStatus
    indexed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    file_hash: str = ""


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int


class DocumentUploadResponse(BaseModel):
    message: str
    document_id: str
    filename: str


# ── Health ───────────────────────────────────────────────

class HealthResponse(BaseModel):
    backend: str = "online"
    chromadb: str = "unknown"
    embeddings: str = "unknown"
    gemini: str = "unknown"
    lmstudio: str = "unknown"
    watcher: str = "unknown"


# ── Models ───────────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    available: bool


class ModelsResponse(BaseModel):
    models: List[ModelInfo]


# ── Stats ────────────────────────────────────────────────

class DocsByType(BaseModel):
    file_type: str
    count: int


class StatsResponse(BaseModel):
    total_documents: int = 0
    indexed_documents: int = 0
    pending_documents: int = 0
    failed_documents: int = 0
    total_chunks: int = 0
    dataset_size_bytes: int = 0
    total_queries: int = 0
    avg_response_time_ms: float = 0.0
    avg_confidence: float = 0.0
    documents_by_type: List[DocsByType] = []


# ── Internal ─────────────────────────────────────────────

class ChunkRecord(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    metadata: Dict[str, Any] = {}
    embedding: Optional[List[float]] = None


class RetrievedChunk(BaseModel):
    chunk_id: str = Field(default="")
    document_id: str = Field(default="")
    text: str = Field(default="")
    score: float = Field(default=0.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="semantic")

    @field_validator("chunk_id", "document_id", "text", "source", mode="before")
    @classmethod
    def coerce_none_to_str(cls, v):
        """Coerce None values to empty string to prevent Pydantic validation errors."""
        if v is None:
            return ""
        return v

