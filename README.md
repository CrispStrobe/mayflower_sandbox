# Mayflower Sandbox

[![CI](https://github.com/mayflower/mayflower_sandbox/actions/workflows/ci.yml/badge.svg)](https://github.com/mayflower/mayflower_sandbox/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![mypy](https://img.shields.io/badge/type--checked-mypy-blue.svg)](https://mypy-lang.org/)
[![Security: Bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://bandit.readthedocs.io/)
[![SBOM: CycloneDX](https://img.shields.io/badge/SBOM-CycloneDX-blue.svg)](https://cyclonedx.org/)

Production-ready Python sandbox implementing the [DeepAgents](https://github.com/mayflower/deepagents) `SandboxBackendProtocol`, with persistent virtual filesystem and document processing helpers.

## Key Features

- **Secure Python Execution** -- Pyodide WebAssembly sandbox with configurable network access
- **Shell Execution** -- BusyBox WASM sandbox with pipe support (`echo | cat | grep`)
- **Persistent Virtual Filesystem** -- PostgreSQL or SQLite-backed storage (20MB per file)
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
