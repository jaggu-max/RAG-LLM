"""RAG pipeline orchestrator — the main intelligence layer with query routing."""

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
from app.rag.prompts import GENERAL_KNOWLEDGE_PROMPT, get_prompt_for_intent
from app.rag.query_router import QueryIntent, QueryPlan, route_query
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
    from app.providers.local_qwen_provider import local_qwen_provider
    active_model = local_qwen_provider.get_selected_model()
    return local_qwen_provider.generate, local_qwen_provider.stream_generate, active_model


def _get_conversation_history(conversation_id: str) -> List[dict]:
    """Get recent conversation history for follow-up resolution."""
    limit = getattr(settings, "CONVERSATION_MEMORY_LIMIT", 10)
    return get_recent_messages(conversation_id, limit=limit)


def _preprocess_query(query: str, conversation_id: str) -> str:
    """Preprocess query — include recent conversation history context for follow-up resolution."""
    history = _get_conversation_history(conversation_id)
    if not history:
        return query

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

    generate_fn, _, model_name = _get_llm_functions(model)

    try:
        # Step 1: Get conversation history
        history = _get_conversation_history(conversation_id)

        # Step 2: Route the query
        plan = route_query(query, conversation_history=history)
        log.info(
            "Pipeline: intent=%s identifiers=%s fields=%s",
            plan.intent.value, plan.identifiers, plan.target_fields,
        )

        # Step 3: Check if knowledge base should be used
        if not request.use_knowledge_base or chroma_count() == 0:
            return _general_knowledge_response(
                query, generate_fn, model_name, conversation_id, start_time
            )

        # Step 4: Determine effective search query
        search_query = query
        if plan.resolved_query:
            search_query = plan.resolved_query
        elif plan.intent == QueryIntent.FOLLOW_UP:
            # Use context-enriched query for follow-ups
            search_query = _preprocess_query(query, conversation_id)

        # Step 5: Multi-strategy hybrid retrieval
        candidates, semantic_count, keyword_count = hybrid_search(
            search_query, plan=plan
        )

        # Step 6: Rerank with intent awareness
        reranked = rerank(search_query, candidates, plan=plan)
        if not reranked and candidates:
            reranked = candidates[:10]
        reranked_count = len(reranked)

        # Step 7: Calculate confidence
        confidence = calculate_confidence(reranked, query, plan=plan) if reranked else 0.0

        # Step 8: Build context with plan awareness
        context = build_context(reranked, plan=plan) if reranked else "No matching documents found."

        # Step 9: Select prompt based on intent
        prompt_template = get_prompt_for_intent(plan.intent)
        system = prompt_template.format(context=context)

        # Step 10: Generate answer & clean residual evidence markers
        raw_answer = generate_fn(query, system_prompt=system, model_name=model_name)
        answer = _clean_answer_text(raw_answer)

        # Step 11: Build deduplicated sources
        sources, unique_source_count = _build_deduplicated_sources(reranked)

        elapsed = int((time.time() - start_time) * 1000)

        # Log query
        log_query(query, "dataset", confidence, model_name, elapsed)

        # Store in conversation
        _store_conversation(
            conversation_id, query, answer,
            model=model_name, answer_type="dataset", confidence=confidence,
            sources=[s.model_dump() for s in sources] if sources else []
        )

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
                unique_source_count=unique_source_count,
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
        # Route the query
        history = _get_conversation_history(conversation_id)
        plan = route_query(query, conversation_history=history)

        # Retrieval
        if not request.use_knowledge_base or chroma_count() == 0:
            system = GENERAL_KNOWLEDGE_PROMPT
            answer_type = "general_knowledge"
            confidence = 0.0
            sources = []
            retrieval = {"semantic_results": 0, "keyword_results": 0, "reranked_results": 0}
        else:
            search_query = query
            if plan.resolved_query:
                search_query = plan.resolved_query
            elif plan.intent == QueryIntent.FOLLOW_UP:
                search_query = _preprocess_query(query, conversation_id)

            candidates, sc, kc = hybrid_search(search_query, plan=plan)
            reranked = rerank(search_query, candidates, plan=plan)
            confidence = calculate_confidence(reranked, query, plan=plan)

            if not reranked or not is_confident_enough(confidence):
                system = GENERAL_KNOWLEDGE_PROMPT
                answer_type = "general_knowledge"
                sources = []
            else:
                context = build_context(reranked, plan=plan)
                prompt_template = get_prompt_for_intent(plan.intent)
                system = prompt_template.format(context=context)
                answer_type = "dataset"
                dedup_sources, unique_src_cnt = _build_deduplicated_sources(reranked)
                sources = [s.model_dump() for s in dedup_sources]

            retrieval = {
                "semantic_results": sc,
                "keyword_results": kc,
                "reranked_results": len(reranked),
                "unique_source_count": unique_src_cnt if 'unique_src_cnt' in locals() else 0,
            }

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
        _store_conversation(conversation_id, query, full_answer, model=model_name, answer_type=answer_type, confidence=confidence, sources=sources)

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
    _store_conversation(conversation_id, query, answer, model=model_name, answer_type="general_knowledge", confidence=0.0, sources=[])

    return ChatResponse(
        answer=answer,
        answer_type=AnswerType.GENERAL_KNOWLEDGE,
        confidence=0.0,
        model=model_name,
        retrieval=retrieval or RetrievalInfo(),
        response_time_ms=elapsed,
        conversation_id=conversation_id,
    )


import re

def _clean_answer_text(text: str) -> str:
    """Clean inline evidence references or relevance scores from LLM response."""
    if not text:
        return text
    cleaned = re.sub(r'\([E|e]vidence\s+\d+:[^\)]+\)', '', text)
    cleaned = re.sub(r'\[Source:[^\]]+\]', '', cleaned)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned


def _build_deduplicated_sources(chunks) -> tuple[List[Source], int]:
    """Group retrieved chunks by document_id/file_name into deduplicated source cards."""
    if not chunks:
        return [], 0

    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        meta = chunk.metadata or {}
        doc_id = meta.get("document_id") or meta.get("doc_id") or meta.get("file_name", "Unknown")
        file_name = meta.get("file_name", "") or meta.get("source_document", "Unknown")
        file_type = meta.get("file_type") or (file_name.split(".")[-1].lower() if "." in file_name else "")

        page = meta.get("page_number")
        slide = meta.get("slide_number")
        section = meta.get("section") or meta.get("sheet_name")

        if doc_id not in grouped:
            grouped[doc_id] = {
                "file_name": file_name,
                "document_id": doc_id,
                "file_type": file_type,
                "pages": set(),
                "slides": set(),
                "sections": set(),
                "top_score": chunk.score if hasattr(chunk, "score") else 0.0,
                "top_chunk_id": chunk.chunk_id if hasattr(chunk, "chunk_id") else "",
                "chunk_count": 0,
            }

        group = grouped[doc_id]
        group["chunk_count"] += 1
        score = chunk.score if hasattr(chunk, "score") else 0.0
        if score > group["top_score"]:
            group["top_score"] = score
            group["top_chunk_id"] = chunk.chunk_id if hasattr(chunk, "chunk_id") else ""

        if page is not None and isinstance(page, int) and page > 0:
            group["pages"].add(page)
        if slide is not None and isinstance(slide, int) and slide > 0:
            group["slides"].add(slide)
        if section:
            group["sections"].add(str(section))

    sources: List[Source] = []
    for doc_id, info in grouped.items():
        pages_list = sorted(list(info["pages"]))
        slides_list = sorted(list(info["slides"]))
        sections_str = ", ".join(sorted(list(info["sections"]))) if info["sections"] else None

        source = Source(
            file_name=info["file_name"],
            document_id=info["document_id"],
            file_type=info["file_type"],
            page=pages_list[0] if pages_list else None,
            pages=pages_list,
            slide_number=slides_list[0] if slides_list else None,
            slides=slides_list,
            section=sections_str,
            chunk_id=info["top_chunk_id"],
            chunk_count=info["chunk_count"],
            score=info["top_score"],
        )
        sources.append(source)

    sources.sort(key=lambda s: s.score, reverse=True)
    return sources, len(sources)


def _build_sources(chunks) -> List[Source]:
    """Compatibility wrapper for source building."""
    sources, _ = _build_deduplicated_sources(chunks)
    return sources


def _store_conversation(
    conversation_id: str,
    question: str,
    answer: str,
    model: str = "gemini",
    answer_type: str = "dataset",
    confidence: float = 0.0,
    sources: Optional[Any] = None,
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
            sources=sources,
        )
    except Exception as e:
        log.warning("Failed to store message in SQLite: %s", e)
