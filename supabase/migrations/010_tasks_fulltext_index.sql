-- Add GIN full-text search index on tasks(query, result).
-- History search currently uses ILIKE which does a full table scan.
-- This index supports ts_rank + plainto_tsquery lookups efficiently.

CREATE INDEX CONCURRENTLY IF NOT EXISTS tasks_query_result_fts
  ON tasks USING GIN (
    to_tsvector('english', coalesce(query, '') || ' ' || coalesce(result, ''))
  );
