"""Retrieval debug endpoint — exposes query plan and search metrics for developer UI."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from app.rag.query_router import route_query
from app.rag.hybrid_search import hybrid_search
from app.rag.reranker import rerank
from app.rag.confidence import calculate_confidence

router = APIRouter()


class DebugQueryRequest(BaseModel):
    query: str


@router.post("/debug/query")
async def debug_query(req: DebugQueryRequest):
    """Analyze query routing, retrieval strategies, and scores without executing full LLM call."""
    plan = route_query(req.query)

    candidates, sem_count, kw_count = hybrid_search(req.query, plan=plan)
    reranked = rerank(req.query, candidates, plan=plan)
    confidence = calculate_confidence(reranked, req.query, plan=plan) if reranked else 0.0

    return {
        "query": req.query,
        "plan": {
            "intent": plan.intent.value,
            "identifiers": plan.identifiers,
            "target_fields": plan.target_fields,
            "target_page": plan.target_page,
            "is_follow_up": plan.is_follow_up,
            "resolved_query": plan.resolved_query,
        },
        "retrieval": {
            "semantic_count": sem_count,
            "keyword_count": kw_count,
            "total_candidates": len(candidates),
            "reranked_count": len(reranked),
            "confidence_score": confidence,
        },
        "top_chunks": [
            {
                "chunk_id": c.chunk_id,
                "score": c.score,
                "source": c.source,
                "document": c.metadata.get("file_name", ""),
                "page": c.metadata.get("page_number"),
                "identifier": c.metadata.get("identifier"),
                "snippet": c.text[:200] + "..." if len(c.text) > 200 else c.text,
            }
            for c in reranked[:5]
        ]
    }
