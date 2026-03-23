-- VFS Snapshots Support
ALTER TABLE sandbox_sessions
ADD COLUMN parent_thread_id TEXT REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE;
