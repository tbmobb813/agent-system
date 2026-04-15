-- Documents and document_chunks tables for RAG (retrieval-augmented generation).
-- Supports PDF, DOCX, TXT, MD ingestion with optional pgvector embeddings.

CREATE TABLE IF NOT EXISTS documents (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL DEFAULT 'default',
    filename    TEXT        NOT NULL,
    file_type   TEXT        NOT NULL,
    file_size   INTEGER     NOT NULL,
    chunk_count INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_user_id   ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_created   ON documents(created_at DESC);

CREATE TABLE IF NOT EXISTS document_chunks (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id  UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  INTEGER     NOT NULL,
    content      TEXT        NOT NULL,
    token_count  INTEGER,
    embedding    vector(1536),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_document  ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
