"""Chat API route — query the RAG pipeline."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest, ChatResponse
from app.rag.pipeline import process_query, process_query_stream

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a query to the RAG pipeline and receive a response."""
    return process_query(request)


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream a response from the RAG pipeline using SSE."""
    return StreamingResponse(
        process_query_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
