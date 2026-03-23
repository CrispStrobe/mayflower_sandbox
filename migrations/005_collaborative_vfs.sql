-- Collaborative VFS Support
ALTER TABLE sandbox_sessions
ADD COLUMN vfs_id TEXT;

-- Initialize vfs_id to thread_id for existing sessions
UPDATE sandbox_sessions SET vfs_id = thread_id WHERE vfs_id IS NULL;

-- Make vfs_id NOT NULL for future
-- (SQLite doesn't support NOT NULL on ALTER TABLE easily, so we handle it in code/new schema)

ALTER TABLE sandbox_filesystem
ADD COLUMN vfs_id TEXT;

UPDATE sandbox_filesystem SET vfs_id = thread_id WHERE vfs_id IS NULL;

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_sandbox_filesystem_vfs_id ON sandbox_filesystem(vfs_id);
