"""
Document Ingestion — parse, chunk, embed, and store documents for RAG.

Supported types: PDF, DOCX, TXT, MD
Storage: Supabase document_chunks table with pgvector embeddings
Search:  Semantic (cosine) if OPENAI_API_KEY set, else full-text
"""

import asyncio
import io
import uuid
import logging
from datetime import datetime
from typing import Optional

import tiktoken

from app.config import settings
from app import database as _db
from app.agent.memory import _embed

logger = logging.getLogger(__name__)

CHUNK_TOKENS   = 400   # target tokens per chunk
CHUNK_OVERLAP  = 50    # overlap tokens between adjacent chunks
MAX_CHUNKS     = 500   # hard cap per document

_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        try:
            _tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tokenizer = None
    return _tokenizer


def _count_tokens(text: str) -> int:
    enc = _get_tokenizer()
    if enc:
        return len(enc.encode(text))
    return len(text) // 4


def _token_chunks(text: str, chunk_tokens: int = CHUNK_TOKENS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping token-based chunks."""
    enc = _get_tokenizer()
    if enc:
        tokens = enc.encode(text)
        chunks = []
        start = 0
        while start < len(tokens):
            end = min(start + chunk_tokens, len(tokens))
            chunk_text = enc.decode(tokens[start:end])
            chunks.append(chunk_text)
            if end == len(tokens):
                break
            start += chunk_tokens - overlap
        return chunks
    else:
        # Fallback: character-based split (~4 chars/token)
        size = chunk_tokens * 4
        overlap_chars = overlap * 4
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append(text[start:end])
            if end == len(text):
                break
            start += size - overlap_chars
        return chunks


# ─────────────────────────────────────────────────────────────────────────────
# Parsers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_pdf(data: bytes) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"PDF parse failed: {e}")
        raise ValueError(f"Could not parse PDF: {e}")


def _parse_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        logger.error(f"DOCX parse failed: {e}")
        raise ValueError(f"Could not parse DOCX: {e}")


def _parse_text(data: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_document(filename: str, data: bytes) -> str:
    """Parse raw file bytes into plain text based on file extension."""
    name = filename.lower()
    if name.endswith(".pdf"):
        return _parse_pdf(data)
    elif name.endswith(".docx"):
        return _parse_docx(data)
    elif name.endswith((".txt", ".md", ".rst", ".csv", ".json", ".yaml", ".yml")):
        return _parse_text(data)
    else:
        # Try plain text for anything else
        try:
            return _parse_text(data)
        except Exception:
            raise ValueError(f"Unsupported file type: {filename}")


# ─────────────────────────────────────────────────────────────────────────────
# Ingest pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def ingest_document(
    filename: str,
    data: bytes,
    user_id: Optional[str] = None,
) -> dict:
    """
    Full pipeline: parse → chunk → embed → store.
    Returns summary dict with document_id and chunk_count.
    """
    if not _db.db_pool:
        raise RuntimeError("Database not connected")

    user_id = user_id or "default"
    file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    # 1. Parse
    text = parse_document(filename, data)
    if not text.strip():
        raise ValueError("Document appears to be empty or unreadable")

    # 2. Chunk
    raw_chunks = _token_chunks(text)
    chunks = raw_chunks[:MAX_CHUNKS]
    if len(raw_chunks) > MAX_CHUNKS:
        logger.warning(f"Document {filename} truncated to {MAX_CHUNKS} chunks (was {len(raw_chunks)})")

    # 3. Create document record
    doc_id = str(uuid.uuid4())
    async with _db.db_pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO documents (id, user_id, filename, file_type, file_size, chunk_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            doc_id, user_id, filename, file_type, len(data), len(chunks), datetime.utcnow(),
        )

    # 4. Embed all chunks in parallel, then store
    token_counts = [_count_tokens(c) for c in chunks]
    embeddings = await asyncio.gather(*[_embed(c) for c in chunks])

    stored = 0
    now = datetime.utcnow()
    async with _db.db_pool.acquire() as conn:
        for i, (chunk_text, token_count, embedding) in enumerate(
            zip(chunks, token_counts, embeddings)
        ):
            if embedding:
                await conn.execute(
                    """
                    INSERT INTO document_chunks
                        (id, document_id, chunk_index, content, token_count, embedding, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6::vector, $7)
                    """,
                    str(uuid.uuid4()), doc_id, i, chunk_text,
                    token_count, str(embedding), now,
                )
            else:
                await conn.execute(
                    """
                    INSERT INTO document_chunks
                        (id, document_id, chunk_index, content, token_count, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    str(uuid.uuid4()), doc_id, i, chunk_text,
                    token_count, now,
                )
            stored += 1

    logger.info(f"Ingested {filename}: {stored} chunks stored (doc_id={doc_id})")
    return {
        "document_id": doc_id,
        "filename": filename,
        "file_type": file_type,
        "chunk_count": stored,
        "total_tokens": sum(_count_tokens(c) for c in chunks),
        "embeddings": stored if settings.OPENAI_API_KEY else 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Search
# ─────────────────────────────────────────────────────────────────────────────

async def search_documents(
    query: str,
    user_id: Optional[str] = None,
    limit: int = 5,
    document_id: Optional[str] = None,
) -> list[dict]:
    """
    Find relevant document chunks for a query.
    Uses vector search if embeddings available, else full-text.
    """
    if not _db.db_pool:
        return []

    user_id = user_id or "default"
    query_embedding = await _embed(query)

    if query_embedding:
        return await _vector_search_docs(query_embedding, user_id, limit, document_id)
    return await _fulltext_search_docs(query, user_id, limit, document_id)


async def _vector_search_docs(
    embedding: list[float],
    user_id: str,
    limit: int,
    document_id: Optional[str],
) -> list[dict]:
    try:
        async with _db.db_pool.acquire() as conn:
            doc_filter = "AND dc.document_id = $4" if document_id else ""
            params = [str(embedding), user_id, limit]
            if document_id:
                params.append(document_id)

            rows = await conn.fetch(
                f"""
                SELECT dc.id, dc.document_id, dc.chunk_index, dc.content, dc.token_count,
                       d.filename,
                       1 - (dc.embedding <=> $1::vector) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.user_id = $2
                  AND dc.embedding IS NOT NULL
                  {doc_filter}
                ORDER BY dc.embedding <=> $1::vector
                LIMIT $3
                """,
                *params,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Vector search on documents failed: {e}")
        return []


async def _fulltext_search_docs(
    query: str,
    user_id: str,
    limit: int,
    document_id: Optional[str],
) -> list[dict]:
    try:
        async with _db.db_pool.acquire() as conn:
            doc_filter = "AND dc.document_id = $3" if document_id else ""
            params = [user_id, query]
            if document_id:
                params.append(document_id)
            params.append(limit)

            rows = await conn.fetch(
                f"""
                SELECT dc.id, dc.document_id, dc.chunk_index, dc.content, dc.token_count,
                       d.filename,
                       ts_rank(to_tsvector('english', dc.content),
                               plainto_tsquery('english', $2)) AS similarity
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.user_id = $1
                  AND to_tsvector('english', dc.content) @@ plainto_tsquery('english', $2)
                  {doc_filter}
                ORDER BY similarity DESC
                LIMIT ${len(params)}
                """,
                *params,
            )
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"Full-text search on documents failed: {e}")
        return []


async def get_context_for_query(
    query: str,
    user_id: Optional[str] = None,
    limit: int = 4,
    max_chars: int = 3000,
) -> str:
    """
    Search documents and return relevant chunks formatted for injection
    into the LLM system prompt.
    """
    chunks = await search_documents(query, user_id=user_id, limit=limit)
    if not chunks:
        return ""

    lines = ["Relevant content from your documents:"]
    total = 0
    for chunk in chunks:
        header = f"\n[{chunk['filename']} — chunk {chunk['chunk_index']}]"
        snippet = chunk["content"]
        if total + len(snippet) > max_chars:
            snippet = snippet[:max_chars - total]
        lines.append(f"{header}\n{snippet}")
        total += len(snippet)
        if total >= max_chars:
            break

    return "\n".join(lines)


# Module-level singleton shortcut
document_manager_search = search_documents
