# Installation

## Prerequisites

- Python 3.10+
- Deno (for Pyodide execution)
- **Database**: Either PostgreSQL 14+ or SQLite (included with Python)

## Install Deno

```bash
curl -fsSL https://deno.land/install.sh | sh

# Add to PATH (add to ~/.bashrc or ~/.zshrc)
export DENO_INSTALL="$HOME/.deno"
export PATH="$DENO_INSTALL/bin:$PATH"
```

## Install Package

```bash
# Clone repository
git clone <repo-url>
cd mayflower-sandbox

# Install package
pip install -e .

# Install with DeepAgents integration (optional)
pip install -e ".[deepagents]"

# Install development dependencies (optional)
pip install -e ".[dev]"
```

## Database Setup

### Option 1: SQLite (Zero-Config)

No database setup is required. You can simply create a SQLite pool in your code, which will automatically initialize the schema in a local file.

```python
from mayflower_sandbox import create_sqlite_pool
db_pool = await create_sqlite_pool("sandbox.db")
```

### Option 2: PostgreSQL

#### Create Database

```bash
createdb mayflower_test
```

#### Apply Schema

```bash
psql -d mayflower_test -f migrations/001_sandbox_schema.sql
```

This creates the necessary tables for session tracking, file storage, and stateful execution support.

## Environment Variables

Create a `.env` file or export environment variables:

```bash
# PostgreSQL connection
export POSTGRES_HOST=localhost
export POSTGRES_DB=mayflower_test
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
export POSTGRES_PORT=5432

# Optional: For LangGraph examples
export ANTHROPIC_API_KEY=your_key_here
export OPENAI_API_KEY=your_key_here
```

## Verify Installation

```bash
# Run tests
pytest tests/test_executor.py -v

# Should see: 12/12 tests passing ✅
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Get started with the Backend API
- [Backend API Reference](../reference/backend-api.md) - Full method signatures
- [Document Helpers](../reference/document-helpers.md) - Document processing helpers
