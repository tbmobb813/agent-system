-- 001_initial_schema.sql
-- Initial database schema for AI Agent System

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- API Keys
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash TEXT UNIQUE NOT NULL,
    name TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);

-- Tasks table (execution history)
CREATE TABLE IF NOT EXISTS tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    result TEXT,
    status TEXT DEFAULT 'pending',
    cost DECIMAL(10, 4) DEFAULT 0.0,
    model_used TEXT,
    tokens_input INTEGER,
    tokens_output INTEGER,
    execution_time FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_tasks_user_id ON tasks(user_id);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
CREATE INDEX idx_tasks_status ON tasks(status);

-- Task execution steps
CREATE TABLE IF NOT EXISTS task_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    action TEXT,
    tool_used TEXT,
    input JSONB,
    output TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_task_steps_task_id ON task_steps(task_id);

-- User preferences/settings
CREATE TABLE IF NOT EXISTS user_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    preferred_model TEXT,
    max_monthly_cost DECIMAL(10, 2) DEFAULT 30.0,
    enable_notifications BOOLEAN DEFAULT true,
    auto_save_results BOOLEAN DEFAULT true,
    context_window_target FLOAT DEFAULT 0.75,
    timezone TEXT DEFAULT 'UTC',
    data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_settings_user_id ON user_settings(user_id);

-- Long-term memory/embeddings
CREATE TABLE IF NOT EXISTS memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category TEXT NOT NULL, -- 'preference', 'fact', 'pattern', 'context'
    content TEXT NOT NULL,
    embedding vector(1536), -- For semantic search
    relevance_score FLOAT DEFAULT 1.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    accessed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE -- Optional expiration
);

CREATE INDEX idx_memory_user_id ON memory(user_id);
CREATE INDEX idx_memory_category ON memory(category);
CREATE INDEX idx_memory_embedding ON memory USING ivfflat (embedding vector_cosine_ops);

-- Conversation history (for context)
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    thread_id TEXT, -- Optional grouping by conversation
    message_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    archived BOOLEAN DEFAULT false
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_thread_id ON conversations(thread_id);

-- Messages (for context window management)
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL, -- 'user', 'assistant'
    content TEXT NOT NULL,
    tokens INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);

-- View for total message count
CREATE OR REPLACE VIEW conversation_summary AS
SELECT 
    c.id,
    c.user_id,
    c.thread_id,
    COUNT(m.id) as message_count,
    COALESCE(SUM(m.tokens), 0) as total_tokens,
    c.created_at,
    c.updated_at
FROM conversations c
LEFT JOIN messages m ON c.id = m.conversation_id
GROUP BY c.id;

-- Enable RLS (Row Level Security) for multi-user safety
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- RLS Policies (users can only see their own data)
CREATE POLICY "Users can view own data"
    ON users FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can view own tasks"
    ON tasks FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can insert own tasks"
    ON tasks FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update own tasks"
    ON tasks FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Users can view own memory"
    ON memory FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can insert own memory"
    ON memory FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Indexes for common queries
CREATE INDEX idx_tasks_user_created ON tasks(user_id, created_at DESC);
CREATE INDEX idx_memory_user_category ON memory(user_id, category);
