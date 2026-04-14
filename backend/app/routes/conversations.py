"""
Conversations routes — list, view, and delete conversation threads.
"""

from fastapi import APIRouter, Depends
from app.utils.auth import verify_api_key, get_user_id_from_key
from app.agent.conversation import conversation_manager

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
async def list_conversations(
    limit: int = 20,
    api_key: str = Depends(verify_api_key),
):
    """List all conversation threads."""
    user_id = get_user_id_from_key(api_key)
    convos = await conversation_manager.list_conversations(user_id=user_id, limit=limit)
    return {"conversations": convos, "total": len(convos)}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Get full message history for a conversation."""
    messages = await conversation_manager.load_messages(conversation_id, max_turns=50)
    return {"conversation_id": conversation_id, "messages": messages, "total": len(messages)}


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Delete a conversation and all its messages."""
    success = await conversation_manager.delete_conversation(conversation_id)
    return {"status": "deleted" if success else "error", "conversation_id": conversation_id}
