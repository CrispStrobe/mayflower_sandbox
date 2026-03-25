# Mayflower Sandbox

[![CI](https://github.com/mayflower/mayflower_sandbox/actions/workflows/ci.yml/badge.svg)](https://github.com/mayflower/mayflower_sandbox/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/type--checked-mypy-blue.svg)](https://mypy-lang.org/)
[![Security: Bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://bandit.readthedocs.io/)
[![SBOM: CycloneDX](https://img.shields.io/badge/SBOM-CycloneDX-blue.svg)](https://cyclonedx.org/)

Production-ready Python sandbox implementing the [DeepAgents](https://reference.langchain.com/python/deepagents/backends/protocol/SandboxBackendProtocol) `SandboxBackendProtocol`, with persistent virtual filesystem and document processing helpers.

## Key Features

- **Secure Python Execution** -- Pyodide WebAssembly sandbox with configurable network access
- **Shell Execution** -- BusyBox WASM sandbox with pipe support (`echo | cat | grep`)
- **Persistent Virtual Filesystem** -- PostgreSQL or SQLite-backed storage (20MB per file)
- **VFS Snapshotting** -- Create point-in-time snapshots of the entire VFS and memory state for experimentation and rollback
- **Fine-grained Network Control** -- Restrict network egress to specific domains (e.g., only GitHub and PyPI)
- **Collaborative VFS** -- Decoupled VFS allows multiple threads/agents to share a single workspace
- **Persistent Library Caching** -- Cache `micropip` wheel files in the database for 90% faster subsequent installs
- **Cross-Language Eval** -- Execute TypeScript code from within Python via the `eval_ts()` bridge
- **Sandbox Debugging** -- Attach standard Chrome/VS Code debuggers to the Pyodide/Deno event loop
- **Zero-Config Mode** -- Full support for SQLite for easy local development and lightweight deployments
- **Document Processing** -- Built-in helpers for Word, Excel, PowerPoint, and PDF
- **Stateful Execution** -- Variables and state persist across executions and restarts
- **Thread Isolation** -- Complete isolation between users/sessions via `thread_id`
- **DeepAgents Integration** -- Implements `SandboxBackendProtocol` and `BackendProtocol`
- **Skills & MCP** -- Install Claude Skills and bind MCP servers as typed Python code
- **Worker Pool** -- 70-95% faster execution by keeping Pyodide loaded in memory

## Quick Start (SQLite - Zero Config)

```bash
pip install -e .
```

```python
from mayflower_sandbox import MayflowerSandboxBackend, create_sqlite_pool

# No database setup required. Tables are created automatically on first run.
db_pool = await create_sqlite_pool("sandbox.db")

backend = MayflowerSandboxBackend(
    db_pool, thread_id="user_123",
    allow_net=False, stateful=True,
)

result = await backend.aexecute("print('hello world')")
```

## Interactive Gradio Demo

Mayflower Sandbox includes a Gradio chatbot demo (`demo/app.py`) that showcases usage with various LLM providers.

### Key Demo Features
- **Multi-Provider Support** -- Scaleway, Mistral, OpenRouter, Groq, OpenAI, and local Ollama
- **Automatic Tool-Calling** -- The LLM automatically decides when to use Python or Shell
- **Dynamic File Display** -- Plots and generated files (CSV, PDF, etc.) are shown inline and are downloadable
- **Conversation Persistence** -- Variables and files persist across turns within the same chat session
- **Smart Model Fetching** -- Dynamic model list loading from provider APIs
- **Memory Optimized** -- Robust handling of large data structures to prevent sandbox memory errors

### Running the Demo

1. **Configure Environment** -- Create a `.env` file in the project root with your API keys:
   ```bash
   MISTRAL_API_KEY=your_key
   OPENROUTER_API_KEY=your_key
   GROQ_API_KEY=your_key
   # ... etc
   ```

2. **Install Dependencies**:
   ```bash
   pip install -e ".[demo]"
   ```

3. **Launch**:
   ```bash
   python demo/app.py
   ```
   The UI will be available at `http://localhost:7860`.

## Core Features

### VFS Snapshotting & Branching

Create a complete point-in-time clone of your sandbox state (files and variables) to safely try complex edits.

```python
# Create a snapshot
snapshot_id = await backend.acreate_snapshot(ttl_days=1)

# ... experiment, delete files, etc ...

# Roll back to the saved state
await backend.arestore_snapshot(snapshot_id)
```

Snapshots are automatically cleaned up when the parent session expires or after the specified TTL.

### Fine-grained Network Control

Secure your sandbox by whitelisting only the domains your agent needs.

```python
backend = MayflowerSandboxBackend(
    db_pool, 
    thread_id="user_123",
    allow_net=["api.github.com", "pypi.org"] # Strict whitelist
)

# This will succeed
await backend.aexecute("python -c \"import requests; requests.get('https://api.github.com')\"")

# This will fail with a NetworkError (blocked by Deno)
await backend.aexecute("python -c \"import requests; requests.get('https://malicious-site.com')\"")
```

### Collaborative VFS Workspaces

Allow multiple agents or threads to share the same persistent storage workspace.

```python
# Agent A and B share the same workspace
backend_a = MayflowerSandboxBackend(db_pool, "agent_a", vfs_id="project_workspace")
backend_b = MayflowerSandboxBackend(db_pool, "agent_b", vfs_id="project_workspace")

await backend_a.awrite("/code.py", "print('hello')")
content = await backend_b.aread("/code.py") # Accesses shared workspace
```

### Cross-Language Eval (`eval_ts`)

Execute TypeScript directly from your Python sandbox via the MCP bridge.

```python
code = """
res = await eval_ts("console.log(1+2)")
print(res['stdout']) # outputs 3
"""
await backend.aexecute(code)
```

### Sandbox Debugging

Enable the Deno inspector to debug complex issues using standard tools.

```python
backend = MayflowerSandboxBackend(db_pool, "user_123", enable_debugger=True)
# Worker starts with --inspect, connect via Chrome DevTools or VS Code
```

### Persistent Library Caching

Drastically reduce sandbox initialization time by caching `micropip` wheel files in the database.

```python
# First run: downloads and caches
await backend.aexecute("import micropip; await micropip.install('numpy')")

# Subsequent runs (even after restart): loads from DB cache (~90% faster)
await backend.aexecute("import micropip; await micropip.install('numpy')")
```

## Reliability

Mayflower Sandbox is rigorously tested to ensure production-grade reliability across both database backends.

- **514+ Tests Passing** -- Full suite verified for both PostgreSQL and SQLite
- **Multi-Database Parity** -- Guaranteed identical behavior between Postgres and SQLite implementations
- **Zero-Config Ready** -- Automatic migrations and SQL translation for immediate deployment

## Quick Start (PostgreSQL)

```bash
pip install -e .
createdb mayflower_test
psql -d mayflower_test -f migrations/001_sandbox_schema.sql
```

```python
import asyncpg
from mayflower_sandbox import MayflowerSandboxBackend

db_pool = await asyncpg.create_pool(
    host="localhost", database="mayflower_test",
    user="postgres", password="postgres",
)

backend = MayflowerSandboxBackend(db_pool, thread_id="user_123")
```

## Development & Testing

Mayflower Sandbox includes a comprehensive test suite that can run against either database backend.

### Run tests with SQLite (Fastest)
```bash
export MAYFLOWER_USE_SQLITE=true
pytest
```

### Run tests with PostgreSQL
Ensure you have a local PostgreSQL instance running on port 5432 (or configure via env vars).
```bash
pytest
```

## Documentation

- **Getting Started** -- [Installation](docs/getting-started/installation.md) | [Quick Start](docs/getting-started/quickstart.md)
- **How-To Guides** -- [Document Processing](docs/how-to/document-processing.md) | [Skills & MCP](docs/how-to/skills-and-mcp.md) | [Deployment](docs/how-to/deployment.md) | [Troubleshooting](docs/how-to/troubleshooting.md)
- **Reference** -- [Backend API](docs/reference/backend-api.md) | [Configuration](docs/reference/configuration.md) | [Document Helpers](docs/reference/document-helpers.md) | [Internal API](docs/reference/api.md)
- **Architecture** -- [System Design](docs/architecture/system-design.md) | [Command Routing](docs/architecture/command-routing.md) | [Security Model](docs/architecture/security-model.md) | [Performance](docs/architecture/performance.md)

## License

MIT

## Related Projects

- [DeepAgents](https://github.com/mayflower/deepagents) -- Agent framework with `SandboxBackendProtocol`
- [Pyodide](https://pyodide.org/) -- Python in WebAssembly
- [BusyBox](https://busybox.net/) -- Unix utilities in a single executable
