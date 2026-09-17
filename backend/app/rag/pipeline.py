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


def _get_image_document() -> Optional[dict]:
    """Find the most recent image document in the system."""
    from app.models.database import list_documents
    docs = list_documents()
    for d in docs:
        if d.get("file_type", "").lower() in ("image", "png", "jpg", "jpeg", "webp"):
            return d
    return None


def _vision_answer_from_image(query: str, doc: dict) -> str:
    """Analyze original image directly using Vision LLM when OCR retrieval is low confidence."""
    import base64
    from pathlib import Path
    import requests

    filepath = Path(doc["file_path"])
    if not filepath.exists():
        return ""
    try:
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate"
        with open(filepath, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            f"You are NEXUS, an enterprise knowledge assistant analyzing an uploaded image/handwritten document ({doc['filename']}).\n"
            f"Question: {query}\n\n"
            f"Read and transcribe the image text accurately, then answer the question directly based ONLY on the contents of this image."
        )

        payload = {
            "model": "gemma3:4b",
            "prompt": prompt,
            "images": [b64_img],
            "stream": False,
        }

        resp = requests.post(url, json=payload, timeout=25)
        if resp.status_code == 200:
            return resp.json().get("response", "").strip()
    except Exception as e:
        log.warning("Direct vision LLM answer failed for %s: %s", doc["filename"], e)
    return ""


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
            search_query = _preprocess_query(query, conversation_id)

        # Step 5: Multi-strategy hybrid retrieval
        candidates, semantic_count, keyword_count = hybrid_search(
            search_query, plan=plan
        )

        # If query is about an image or handwritten note, isolate image candidates
        is_image_intent = plan.intent == QueryIntent.IMAGE_NOTE
        if is_image_intent and candidates:
            img_candidates = []
            for c in candidates:
                meta = getattr(c, "metadata", {}) or {}
                fn = str(meta.get("file_name", "") or meta.get("source_document", "")).lower()
                ft = str(meta.get("file_type", "")).lower()
                st = str(meta.get("source_type", "")).lower()
                if ft in ("image", "png", "jpg", "jpeg", "webp") or st == "image" or any(fn.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                    img_candidates.append(c)
            if img_candidates:
                candidates = img_candidates

        # Step 6: Rerank with intent awareness
        reranked = rerank(search_query, candidates, plan=plan)
        if not reranked and candidates:
            reranked = candidates[:10]
        reranked_count = len(reranked)

        # Step 7: Calculate confidence
        confidence = calculate_confidence(reranked, query, plan=plan) if reranked else 0.0

        # Step 8: Image Vision Fallback if image query but OCR retrieval confidence is low (< 0.25)
        if is_image_intent and (confidence < 0.25 or not reranked):
            img_doc = _get_image_document()
            if img_doc:
                log.info("Low OCR confidence for image query. Using direct Vision LLM fallback for %s...", img_doc["filename"])
                vision_answer = _vision_answer_from_image(query, img_doc)
                if vision_answer:
                    elapsed = int((time.time() - start_time) * 1000)
                    sources = [Source(
                        file_name=img_doc["filename"],
                        document_id=img_doc["id"],
                        file_type=img_doc["file_type"],
                        page=1,
                        pages=[1],
                        chunk_count=1,
                        score=0.95,
                        snippet=vision_answer[:200],
                    )]
                    log_query(query, "dataset", 0.95, model_name, elapsed)
                    _store_conversation(conversation_id, query, vision_answer, model=model_name, answer_type="dataset", confidence=0.95, sources=[s.model_dump() for s in sources])
                    return ChatResponse(
                        answer=vision_answer,
                        answer_type=AnswerType.DATASET,
                        confidence=0.95,
                        model=model_name,
                        sources=sources,
                        retrieval=RetrievalInfo(semantic_results=1, keyword_results=0, reranked_results=1, unique_source_count=1),
                        response_time_ms=elapsed,
                        conversation_id=conversation_id,
                    )

        # Step 9: Build context with plan awareness
        context = build_context(reranked, plan=plan) if reranked else "No matching documents found."

        # Step 10: Select prompt based on intent
        prompt_template = get_prompt_for_intent(plan.intent)
        system = prompt_template.format(context=context)

        # Step 11: Generate answer & clean residual evidence markers
        raw_answer = generate_fn(query, system_prompt=system, model_name=model_name)
        answer = _clean_answer_text(raw_answer)

        # Step 12: Build strictly relevant deduplicated sources
        # Only include chunks with score >= minimum relevance threshold
        CITATION_SCORE_MIN = 0.28
        CITATION_TOP_K = 3  # max number of distinct source documents to cite

        # For image-intent queries, enforce strict image-document isolation regardless of score
        if is_image_intent:
            reranked_for_sources = [
                c for c in reranked
                if _chunk_is_image_doc(c)
            ]
            # Fallback: if no image chunks survived, still use top image chunk from all candidates
            if not reranked_for_sources and candidates:
                for c in candidates:
                    if _chunk_is_image_doc(c):
                        reranked_for_sources.append(c)
                        break
        else:
            # Score-filter: only include chunks that meet minimum relevance threshold
            reranked_for_sources = [
                c for c in reranked
                if (getattr(c, 'score', 0.0) or 0.0) >= CITATION_SCORE_MIN
            ]

        sources, unique_source_count = _build_deduplicated_sources(
            reranked_for_sources, top_k_docs=CITATION_TOP_K
        )

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

                # Strict relevance filtering for citations
                CITATION_SCORE_MIN = 0.28
                CITATION_TOP_K = 3
                is_img_intent = plan.intent == QueryIntent.IMAGE_NOTE
                if is_img_intent:
                    reranked_for_sources = [c for c in reranked if _chunk_is_image_doc(c)]
                    if not reranked_for_sources and candidates:
                        for c in candidates:
                            if _chunk_is_image_doc(c):
                                reranked_for_sources.append(c); break
                else:
                    reranked_for_sources = [c for c in reranked if (getattr(c, 'score', 0.0) or 0.0) >= CITATION_SCORE_MIN]

                dedup_sources, unique_src_cnt = _build_deduplicated_sources(reranked_for_sources, top_k_docs=CITATION_TOP_K)
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


def _chunk_is_image_doc(chunk) -> bool:
    """Return True if this chunk belongs to an image/photo document."""
    meta = getattr(chunk, 'metadata', {}) or {}
    ft = str(meta.get('file_type', '') or getattr(chunk, 'file_type', '')).lower()
    fn = str(meta.get('file_name', '') or meta.get('source_document', '') or getattr(chunk, 'file_name', '')).lower()
    return ft in ('image', 'png', 'jpg', 'jpeg', 'webp') or any(fn.endswith(ext) for ext in ('.jpg', '.jpeg', '.png', '.webp'))


def _build_deduplicated_sources(chunks, top_k_docs: int = 4) -> tuple[List[Source], int]:
    """Group retrieved chunks by document_id/file_name into deduplicated source cards.
    Only the top top_k_docs distinct documents are returned.
    """
    if not chunks:
        return [], 0

    grouped: Dict[str, Dict[str, Any]] = {}
    for chunk in chunks:
        meta = getattr(chunk, "metadata", {}) or {}
        doc_id = getattr(chunk, "document_id", "") or meta.get("document_id") or meta.get("doc_id") or meta.get("file_name", "Unknown")
        file_name = meta.get("file_name", "") or getattr(chunk, "file_name", "") or meta.get("source_document", "Unknown")
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
                "top_text": chunk.text if hasattr(chunk, "text") else "",
                "chunk_count": 0,
            }

        group = grouped[doc_id]
        group["chunk_count"] += 1
        score = chunk.score if hasattr(chunk, "score") else 0.0
        if score >= group["top_score"]:
            group["top_score"] = score
            group["top_chunk_id"] = chunk.chunk_id if hasattr(chunk, "chunk_id") else ""
            if hasattr(chunk, "text") and chunk.text:
                group["top_text"] = chunk.text

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
            snippet=info.get("top_text", ""),
        )
        sources.append(source)

    sources.sort(key=lambda s: s.score, reverse=True)
    # Cap to top_k_docs distinct documents
    sources = sources[:top_k_docs]
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
