# Security Model

How Mayflower Sandbox isolates untrusted code execution and protects the host system.

## Sandboxing Layers

### 1. WebAssembly Sandbox

All code execution happens inside WebAssembly:

- **Python** runs in [Pyodide](https://pyodide.org/) (CPython compiled to WASM)
- **Shell commands** run in BusyBox compiled to WASM

WebAssembly provides memory isolation by design -- sandbox code cannot access the host filesystem, network, or memory space outside its own linear memory.

### 2. Deno Permission Model

Deno's permission system provides a second layer:

- `--allow-read` scoped to the executor script only
- `--allow-net` controlled per execution (`allow_net` parameter)
- No `--allow-write` to the host filesystem
- No `--allow-env` access to host environment

### 3. Worker-Based Isolation

Shell pipelines use separate Deno Workers per stage:

```
echo hello | cat | grep hello
     |         |         |
  Worker 1   Worker 2   Worker 3
```

Each Worker gets its own BusyBox WASM instance, preventing global-state contamination between pipeline stages.

## Thread & Workspace Isolation

Data isolation is enforced via the database schema using both `thread_id` and `vfs_id`:

- **Isolation by Default**: By default, `vfs_id` equals `thread_id`, providing complete isolation between users.
- **Collaborative Workspaces**: By explicitly providing a shared `vfs_id`, multiple threads can access the same persistent storage pool while maintaining separate execution memory.
- **Foreign Key Constraints**: Files are partitioned by `vfs_id`, and sessions are isolated by `thread_id`.

```sql
-- VFS isolation is based on vfs_id
PRIMARY KEY (vfs_id, file_path)
FOREIGN KEY (thread_id) REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE
```

## VFS Snapshots

Snapshots allow creating transient, isolated clones of session state:
- **Instant Rollback**: Clones the entire VFS and memory state into a new `thread_id`.
- **Automatic Cleanup**: Snapshots are linked to the parent thread via `parent_thread_id` and use `ON DELETE CASCADE`. Deleting the parent thread automatically purges all its snapshots.

## Path Validation

All file operations validate paths before accessing the database:

- Paths must be absolute (start with `/`)
- No `..` directory traversal components allowed
- No invalid or control characters
- Length limits enforced

Path validation happens in the backend layer before any VFS operation, preventing injection attacks regardless of how the backend is called.

## File Size Limits

Files are limited to **20MB** each, enforced at the database level:

```sql
content BYTEA NOT NULL CHECK (octet_length(content) <= 20971520)
```

This prevents denial-of-service through excessive storage consumption.

## Network Access Control

Network access is disabled by default and can be configured with high precision:

- **Disabled** (`allow_net=False`): No outbound network access.
- **Full Access** (`allow_net=True`): Allows all outbound traffic.
- **Fine-grained Allowlist** (`allow_net=["api.github.com"]`): Only permits traffic to specific domains.
- **Mandatory Defaults**: Critical infrastructure domains (e.g., PyPI, `cdn.jsdelivr.net` for Pyodide, and `127.0.0.1` for the MCP bridge) are automatically whitelisted when any network access is enabled.

Enforcement happens at the **Deno capability boundary**, ensuring that even compromised sandbox code cannot escape the specified allowlist.

## Session Expiration

Sessions expire automatically after **180 days** (configurable). The `CleanupJob` periodically:

1. Finds expired sessions (`expires_at < NOW()`)
2. Deletes all associated files (cascading foreign key)
3. Deletes session state
4. Deletes session records

This prevents indefinite storage growth from abandoned sessions.

## MCP Security

When binding external MCP servers:

- `MAYFLOWER_MCP_ALLOWLIST` restricts which servers can be bound (name or host-suffix matching)
- MCP calls are rate-limited (`MAYFLOWER_MCP_CALL_INTERVAL`, default 0.1s)
- Sessions have a TTL (`MAYFLOWER_MCP_SESSION_TTL`, default 5 minutes)
- All MCP traffic is proxied through a localhost bridge -- Pyodide never contacts external servers directly
