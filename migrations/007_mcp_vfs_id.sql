-- Add vfs_id to sandbox_mcp_servers
ALTER TABLE sandbox_mcp_servers ADD COLUMN vfs_id TEXT;
UPDATE sandbox_mcp_servers SET vfs_id = thread_id WHERE vfs_id IS NULL;
