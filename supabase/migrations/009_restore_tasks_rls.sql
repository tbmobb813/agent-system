-- Re-enable RLS on tasks after relaxing the user_id column for single-user mode.
-- Keep the TEXT user_id change from 008, but deny direct client access by default.
-- The backend uses a direct database connection, while Supabase client roles should
-- not be able to read or mutate task history unless explicit policies are added later.

ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

-- Intentionally leave public/anon/authenticated roles without policies on tasks.
-- This blocks direct access through Supabase client keys while preserving backend access.