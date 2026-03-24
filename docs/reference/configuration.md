# Configuration Reference

All environment variables, database schema, and tuning parameters for Mayflower Sandbox.

## Supported Databases

Mayflower Sandbox supports both **PostgreSQL** (recommended for production) and **SQLite** (recommended for local development and lightweight deployments).

### SQLite (Zero-Config)

To use SQLite, simply use `create_sqlite_pool("path/to/db.sqlite")` in your code. No environment variables are strictly required, but you can configure the path via your application's own configuration.

### PostgreSQL

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `localhost` | Database host |
| `POSTGRES_DB` | `mayflower_test` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |
| `POSTGRES_PORT` | `5432` | Database port |

### Worker Pool

| Variable | Default | Description |
|----------|---------|-------------|
| `PYODIDE_USE_POOL` | `false` | Enable worker pool (recommended for production) |
| `PYODIDE_POOL_SIZE` | `3` | Number of Deno workers in the pool |
| `PYODIDE_WORKER_REQUEST_LIMIT` | `1000` | Recycle worker after N requests |
| `PYODIDE_HEALTH_CHECK_INTERVAL` | `30` | Health check interval in seconds |

### MCP / Network

| Variable | Default | Description |
|----------|---------|-------------|
| `MAYFLOWER_MCP_ALLOWLIST` | (none) | Comma-separated server names or host suffixes to allow binding |
| `MAYFLOWER_MCP_SESSION_TTL` | `300` | MCP session TTL in seconds (5 minutes) |
| `MAYFLOWER_MCP_CALL_INTERVAL` | `0.1` | Minimum interval between MCP calls in seconds |
| `MAYFLOWER_SANDBOX_NET_ALLOW` | (none) | Additional hosts to allow outbound connections to |

### LLM (for tests and examples)

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | (none) | For LLM-dependent tests |
| `OPENAI_API_KEY` | (none) | Alternative LLM provider |

## Database Schema

Apply the schema with:

```bash
psql -d mayflower_test -f migrations/001_sandbox_schema.sql
```

### sandbox_sessions

Tracks active sessions with automatic expiration and links to snapshots/workspaces.

```sql
CREATE TABLE sandbox_sessions (
    thread_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '180 days',
    metadata JSONB DEFAULT '{}'::jsonb,
    parent_thread_id TEXT REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE,
    vfs_id TEXT
);
```

### sandbox_filesystem

Stores files with a 20MB-per-file limit, partitioned by `vfs_id`.

```sql
CREATE TABLE sandbox_filesystem (
    thread_id TEXT NOT NULL,
    vfs_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content BYTEA NOT NULL CHECK (octet_length(content) <= 20971520),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb,
    PRIMARY KEY (vfs_id, file_path),
    FOREIGN KEY (thread_id) REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE
);
```

### sandbox_session_bytes

Stores serialized Pyodide session state for stateful execution.

```sql
CREATE TABLE sandbox_session_bytes (
    thread_id TEXT PRIMARY KEY,
    session_bytes BYTEA NOT NULL,
    session_metadata JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    FOREIGN KEY (thread_id) REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE
);
```

### sandbox_package_cache

Caches `micropip` wheel files for faster installations.

```sql
CREATE TABLE sandbox_package_cache (
    package_name TEXT NOT NULL,
    version TEXT NOT NULL,
    pyodide_version TEXT NOT NULL,
    filename TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (package_name, version, pyodide_version)
);
```

### sandbox_skills

Tracks installed Claude Skills metadata.

### sandbox_mcp_servers

Stores MCP server bindings and connection metadata.

## Worker Pool Tuning

### Choosing Pool Size

- Each worker uses ~150--200MB RAM with Pyodide loaded
- Default of 3 workers = ~500MB baseline
- Increase for high-concurrency workloads
- Reduce to 1--2 for memory-constrained environments

### Debugger Support

- `enable_debugger=True`: Starts Deno workers with the `--inspect` flag.
- Default port is 9229. If using a pool, ports are assigned dynamically.

## Network Access Control

- Default: Network disabled (`allow_net=False`)
- `allow_net=True`: Enables full outbound network access.
- `allow_net=["domain.com"]`: Restricts egress to specific domains only.
- CDN traffic (`cdn.jsdelivr.net`) and PyPI (`pypi.org`, `files.pythonhosted.org`) are always allowed when any network access is enabled.
- MCP bridge communication uses `127.0.0.1:<port>` (localhost only).
- Use `MAYFLOWER_SANDBOX_NET_ALLOW` to whitelist additional hosts via environment variables.

