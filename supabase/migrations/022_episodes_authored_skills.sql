-- 022_episodes_authored_skills.sql
-- Episodic memory layer: records every agent run as a searchable episode,
-- and stores LLM-authored skill knowledge extracted from complex tasks.
--
-- user_id is TEXT (not a FK) matching the pattern established in migrations
-- 006/008 for this single-user personal agent. RLS is not applied.

-- ── authored_skills ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS authored_skills (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            TEXT,
    name               TEXT        NOT NULL,
    pattern            TEXT        NOT NULL,
    solution           TEXT        NOT NULL,
    preconditions      TEXT[],
    gotchas            TEXT[],
    source_episode_ids UUID[]      NOT NULL DEFAULT '{}',
    use_count          INTEGER     NOT NULL DEFAULT 0,
    success_count      INTEGER     NOT NULL DEFAULT 0,
    embedding          vector(1536),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_authored_skills_user_id
    ON authored_skills(user_id);
CREATE INDEX IF NOT EXISTS idx_authored_skills_embedding
    ON authored_skills USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_authored_skills_use_count
    ON authored_skills(user_id, use_count DESC);

-- ── episodes ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS episodes (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT,
    task_id           UUID        REFERENCES tasks(id) ON DELETE SET NULL,
    session_id        UUID,
    query             TEXT        NOT NULL,
    outcome           TEXT,
    success           BOOLEAN,
    tools_used        TEXT[]      NOT NULL DEFAULT '{}',
    cost_usd          DECIMAL(10,4),
    duration_ms       INTEGER,
    key_learnings     TEXT,
    authored_skill_id UUID        REFERENCES authored_skills(id) ON DELETE SET NULL,
    embedding         vector(1536),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_episodes_user_created
    ON episodes(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_session
    ON episodes(session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_episodes_success
    ON episodes(user_id, success, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodes_embedding
    ON episodes USING ivfflat (embedding vector_cosine_ops);
