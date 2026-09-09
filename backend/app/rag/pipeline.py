"""RAG pipeline orchestrator — the main intelligence layer."""

from __future__ import annotations

import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.models.database import chroma_count, log_query
from app.models.schemas import (
    AnswerType, ChatRequest, ChatResponse, RetrievalInfo, Source,
)
from app.rag.confidence import calculate_confidence, is_confident_enough
from app.rag.context_builder import build_context
from app.rag.hybrid_search import hybrid_search
from app.rag.prompts import GENERAL_KNOWLEDGE_PROMPT, SYSTEM_PROMPT
from app.rag.reranker import rerank
from app.rag.validator import build_insufficient_response, validate_response

log = get_logger(__name__)

from app.models.conversation_db import (
    add_message,
    get_recent_messages,
    create_conversation,
)


def _get_llm_functions(model: str):
    """Return (generate, stream_generate, display_model) for the given model option."""
    if model.lower() == "gemini" or model.startswith("gemini"):
        from app.services import gemini_service
        return gemini_service.generate, gemini_service.stream_generate, "gemini"
    else:
        from app.services import lmstudio_service
        return lmstudio_service.generate, lmstudio_service.stream_generate, "local_qwen"


def _preprocess_query(query: str, conversation_id: str) -> str:
    """Preprocess query — include recent conversation history context for follow-up resolution."""
    limit = getattr(settings, "CONVERSATION_MEMORY_LIMIT", 10)
    history = get_recent_messages(conversation_id, limit=limit)
    if not history:
        return query

    # Format recent conversation history into query context
    history_lines = []
    for msg in history:
        role = "User" if msg["role"] == "user" else "Assistant"
        history_lines.append(f"{role}: {msg['content']}")

    history_str = "\n".join(history_lines)
    expanded = f"Previous Conversation Context:\n{history_str}\n\nCurrent Question: {query}"
    return expanded


def process_query(request: ChatRequest) -> ChatResponse:
    """Main RAG pipeline — synchronous version."""
    start_time = time.time()

    conversation_id = request.conversation_id or uuid.uuid4().hex[:12]
    query = request.message
    model = request.model

    # Get LLM functions
    generate_fn, _, model_name = _get_llm_functions(model)

    try:
        # Step 1: Preprocess query
        processed_query = _preprocess_query(query, conversation_id)
        log.info("Query: %s | Model: %s", query[:100], model)

        # Step 2: Check if knowledge base should be used
        if not request.use_knowledge_base or chroma_count() == 0:
            return _general_knowledge_response(
                query, generate_fn, model_name, conversation_id, start_time
            )

        # Step 3: Hybrid retrieval
        candidates, semantic_count, keyword_count = hybrid_search(processed_query)

        # Step 4: Rerank
        reranked = rerank(processed_query, candidates)
        reranked_count = len(reranked)

        # Step 5: Calculate confidence
        confidence = calculate_confidence(reranked, processed_query)

        # Step 6: Decision — dataset or general knowledge?
        if not reranked or not is_confident_enough(confidence):
            log.info("Low confidence (%.2f) — switching to general knowledge", confidence)
            return _general_knowledge_response(
                query, generate_fn, model_name, conversation_id, start_time,
                retrieval=RetrievalInfo(
                    semantic_results=semantic_count,
                    keyword_results=keyword_count,
                    reranked_results=reranked_count,
                ),
            )

        # Step 7: Build context
        context = build_context(reranked)

        # Step 8: Generate answer
        system = SYSTEM_PROMPT.format(context=context)
        answer = generate_fn(query, system_prompt=system, model_name=model_name)

        # Step 9: Validate
        if not validate_response(answer, context):
            log.warning("Validation failed — regenerating with stricter prompt")
            answer = generate_fn(
                f"STRICTLY answer only from the context. Question: {query}",
                system_prompt=system,
                model_name=model_name,
            )
            if not validate_response(answer, context):
                answer = build_insufficient_response()
                confidence = 0.3

        # Step 10: Build sources
        sources = _build_sources(reranked)

        elapsed = int((time.time() - start_time) * 1000)

        # Log query
        log_query(query, "dataset", confidence, model_name, elapsed)

        # Store in conversation
        _store_conversation(conversation_id, query, answer, model=model_name, answer_type="dataset", confidence=confidence)

        return ChatResponse(
            answer=answer,
            answer_type=AnswerType.DATASET,
            confidence=round(confidence, 4),
            model=model_name,
            sources=sources,
            retrieval=RetrievalInfo(
                semantic_results=semantic_count,
                keyword_results=keyword_count,
                reranked_results=reranked_count,
            ),
            response_time_ms=elapsed,
            conversation_id=conversation_id,
        )

    except RuntimeError as e:
        elapsed = int((time.time() - start_time) * 1000)
        return ChatResponse(
            answer=str(e),
            answer_type=AnswerType.INSUFFICIENT,
            confidence=0.0,
            model=model_name,
            response_time_ms=elapsed,
            conversation_id=conversation_id,
        )
    except Exception as e:
        log.error("Pipeline error: %s", e, exc_info=True)
        elapsed = int((time.time() - start_time) * 1000)
        return ChatResponse(
            answer=f"An error occurred: {str(e)}",
            answer_type=AnswerType.INSUFFICIENT,
            confidence=0.0,
            model=model_name,
            response_time_ms=elapsed,
            conversation_id=conversation_id,
        )


async def process_query_stream(request: ChatRequest) -> AsyncGenerator[str, None]:
    """Streaming version of the RAG pipeline."""
    import json

    conversation_id = request.conversation_id or uuid.uuid4().hex[:12]
    query = request.message
    model = request.model
    start_time = time.time()

    _, stream_fn, model_name = _get_llm_functions(model)

    try:
        processed_query = _preprocess_query(query, conversation_id)

        # Retrieval
        if not request.use_knowledge_base or chroma_count() == 0:
            system = GENERAL_KNOWLEDGE_PROMPT
            context = ""
            answer_type = "general_knowledge"
            confidence = 0.0
            sources = []
            retrieval = {"semantic_results": 0, "keyword_results": 0, "reranked_results": 0}
        else:
            candidates, sc, kc = hybrid_search(processed_query)
            reranked = rerank(processed_query, candidates)
            confidence = calculate_confidence(reranked, processed_query)

            if not reranked or not is_confident_enough(confidence):
                system = GENERAL_KNOWLEDGE_PROMPT
                context = ""
                answer_type = "general_knowledge"
                sources = []
            else:
                context = build_context(reranked)
                system = SYSTEM_PROMPT.format(context=context)
                answer_type = "dataset"
                sources = [s.model_dump() for s in _build_sources(reranked)]

            retrieval = {"semantic_results": sc, "keyword_results": kc, "reranked_results": len(reranked)}

        # Send metadata first
        meta = {
            "type": "metadata",
            "answer_type": answer_type,
            "confidence": round(confidence, 4),
            "model": model_name,
            "sources": sources,
            "retrieval": retrieval,
            "conversation_id": conversation_id,
        }
        yield f"data: {json.dumps(meta)}\n\n"

        # Stream LLM response
        full_answer = ""
        async for chunk in stream_fn(query, system_prompt=system, model_name=model_name):
            full_answer += chunk
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        elapsed = int((time.time() - start_time) * 1000)
        log_query(query, answer_type, confidence, model_name, elapsed)
        _store_conversation(conversation_id, query, full_answer)

        # Send completion
        yield f"data: {json.dumps({'type': 'done', 'response_time_ms': elapsed})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


def _general_knowledge_response(
    query: str, generate_fn, model_name: str,
    conversation_id: str, start_time: float,
    retrieval: RetrievalInfo | None = None,
) -> ChatResponse:
    """Generate a general knowledge response."""
    answer = generate_fn(query, system_prompt=GENERAL_KNOWLEDGE_PROMPT, model_name=model_name)
    elapsed = int((time.time() - start_time) * 1000)
    log_query(query, "general_knowledge", 0.0, model_name, elapsed)
    _store_conversation(conversation_id, query, answer, model=model_name, answer_type="general_knowledge", confidence=0.0)

    return ChatResponse(
        answer=answer,
        answer_type=AnswerType.GENERAL_KNOWLEDGE,
        confidence=0.0,
        model=model_name,
        retrieval=retrieval or RetrievalInfo(),
        response_time_ms=elapsed,
        conversation_id=conversation_id,
    )


def _build_sources(chunks) -> List[Source]:
    """Build source citations from retrieved chunks."""
    sources = []
    seen_files = set()

    for chunk in chunks:
        meta = chunk.metadata
        file_name = meta.get("file_name", "Unknown")

        source = Source(
            file_name=file_name,
            page=meta.get("page_number") if meta.get("page_number") else None,
            section=meta.get("section", "") or meta.get("sheet_name", "") or None,
            chunk_id=chunk.chunk_id,
            score=chunk.score,
            sheet_name=meta.get("sheet_name") or None,
            slide_number=meta.get("slide_number") if meta.get("slide_number") else None,
        )
        sources.append(source)

    return sources


def _store_conversation(
    conversation_id: str,
    question: str,
    answer: str,
    model: str = "gemini",
    answer_type: str = "dataset",
    confidence: float = 0.0,
) -> None:
    """Store user message and assistant response in SQLite database."""
    try:
        add_message(conversation_id=conversation_id, role="user", content=question)
        add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            model=model,
            answer_type=answer_type,
            confidence=confidence,
        )
    except Exception as e:
        log.warning("Failed to store message in SQLite: %s", e)
