"""
Memory routes — view, search, and manage the agent's long-term memory.
"""

from fastapi import APIRouter, Depends, Query
from app.utils.auth import verify_api_key, get_user_id_from_key
from app.agent.memory import memory_manager

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
async def list_memories(
    limit: int = Query(default=20, le=100),
    category: str = Query(default=None),
    api_key: str = Depends(verify_api_key),
):
    """List recent memories."""
    user_id = get_user_id_from_key(api_key)
    memories = await memory_manager.get_recent(
        user_id=user_id, limit=limit, category=category
    )
    return {"memories": memories, "total": len(memories)}


@router.get("/search")
async def search_memories(
    q: str = Query(..., description="Search query"),
    limit: int = Query(default=5, le=20),
    api_key: str = Depends(verify_api_key),
):
    """Search memories by semantic similarity or full-text."""
    user_id = get_user_id_from_key(api_key)
    results = await memory_manager.search(q, user_id=user_id, limit=limit)
    return {"query": q, "results": results, "total": len(results)}


@router.post("")
async def save_memory(
    content: str,
    category: str = "fact",
    api_key: str = Depends(verify_api_key),
):
    """Manually save a memory (facts, preferences, etc.)."""
    user_id = get_user_id_from_key(api_key)
    memory_id = await memory_manager.save(
        content=content, category=category, user_id=user_id
    )
    if not memory_id:
        return {"status": "error", "detail": "Database unavailable"}
    return {"status": "saved", "id": memory_id}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, api_key: str = Depends(verify_api_key)):
    """Delete a specific memory."""
    success = await memory_manager.delete(memory_id)
    return {"status": "deleted" if success else "error", "id": memory_id}
