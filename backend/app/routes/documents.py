"""
Document routes — upload, list, delete, and search ingested documents.
"""

import logging

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from fastapi.responses import JSONResponse

from app.utils.auth import verify_api_key
from app.database import fetch, fetchrow, fetchval, execute, db_pool
from app.agent.documents import ingest_document, search_documents

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key),
):
    """Upload and ingest a document (PDF, DOCX, TXT, MD)."""
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_FILE_SIZE // 1_000_000} MB)")

    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = await ingest_document(filename=file.filename or "upload.txt", data=data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")


@router.get("")
async def list_documents(
    limit: int = Query(20, le=100),
    offset: int = 0,
    api_key: str = Depends(verify_api_key),
):
    """List all ingested documents."""
    if not db_pool:
        return {"documents": [], "total": 0}

    rows = await fetch(
        """
        SELECT id, filename, file_type, file_size, chunk_count, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit, offset,
    )
    total = await fetchval("SELECT COUNT(*) FROM documents") or 0
    return {
        "documents": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Delete a document and all its chunks."""
    doc = await fetchrow("SELECT id FROM documents WHERE id = $1", document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Chunks cascade via FK, so deleting the parent is enough
    await execute("DELETE FROM documents WHERE id = $1", document_id)
    return {"status": "deleted", "document_id": document_id}


@router.get("/search")
async def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(5, le=20),
    document_id: str = Query(None, description="Restrict to a specific document"),
    api_key: str = Depends(verify_api_key),
):
    """Search document chunks semantically or by full-text."""
    results = await search_documents(q, limit=limit, document_id=document_id)
    return {"query": q, "results": results, "total": len(results)}
