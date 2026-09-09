"""API routes for conversation management."""

from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.conversation_db import (
    create_conversation,
    list_conversations,
    get_conversation,
    delete_conversation,
)

router = APIRouter()


class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"


@router.post("/conversations")
async def create_new_conversation(req: CreateConversationRequest = CreateConversationRequest()):
    """Create a new conversation."""
    conv = create_conversation(title=req.title or "New Conversation")
    return conv


@router.get("/conversations")
async def get_all_conversations():
    """List all stored conversations."""
    conversations = list_conversations()
    return {"conversations": conversations}


@router.get("/conversations/{conversation_id}")
async def get_single_conversation(conversation_id: str):
    """Retrieve a single conversation by ID including its messages."""
    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_single_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    success = delete_conversation(conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}
