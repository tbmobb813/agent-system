"""
Document routes — upload, list, delete, and search ingested documents.
"""

import logging
import os

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query, Request

from app.utils.auth import verify_api_key
from app.utils.limiter import limiter
from app.database import fetch, fetchrow, fetchval, execute
from app import database as _db
from app.agent.documents import ingest_document, search_documents

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_FILENAME_LEN = 200


def _sanitise_filename(raw: str | None, content_type: str | None) -> str:
    """Strip path components, normalise extension, cap length."""
    name = os.path.basename((raw or "").strip()) or "upload"
    # Remove null bytes and control characters
    name = "".join(c for c in name if ord(c) >= 32 and c not in "\x00/\\")
    name = name[:MAX_FILENAME_LEN] or "upload"
    # If the basename lost its extension, try to recover one from content-type
    if "." not in name and content_type:
        _ct_map = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "text/plain": ".txt",
            "text/markdown": ".md",
        }
        name += _ct_map.get(content_type.split(";")[0].strip(), ".txt")
    return name


@router.post("/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    api_key: str = Depends(verify_api_key),
):
    """Upload and ingest a document (PDF, DOCX, TXT, MD)."""
    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_FILE_SIZE // 1_000_000} MB)",
        )

    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    safe_name = _sanitise_filename(file.filename, file.content_type)

    try:
        result = await ingest_document(filename=safe_name, data=data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Document ingestion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Ingestion failed")


@router.get("")
async def list_documents(
    limit: int = Query(20, le=100),
    offset: int = 0,
    api_key: str = Depends(verify_api_key),
):
    """List all ingested documents."""
    if not _db.db_pool:
        return {"documents": [], "total": 0}

    rows = await fetch(
        """
        SELECT id, filename, file_type, file_size, chunk_count, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
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


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: str,
    api_key: str = Depends(verify_api_key),
):
    """Return the full extracted text of a document (all chunks joined in order)."""
    doc = await fetchrow(
        "SELECT id, filename, file_type FROM documents WHERE id = $1", document_id
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = await fetch(
        """
        SELECT content FROM document_chunks
        WHERE document_id = $1
        ORDER BY chunk_index
        """,
        document_id,
    )
    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "file_type": doc["file_type"],
        "content": "\n\n".join(r["content"] for r in chunks),
        "chunk_count": len(chunks),
    }


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
