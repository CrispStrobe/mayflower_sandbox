import asyncio
import importlib.util
import os
import shutil
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Optional: Redirect all asyncpg pools to SQLite for testing
if os.environ.get("MAYFLOWER_USE_SQLITE") == "true":
    try:
        import asyncpg
        from mayflower_sandbox.db import create_sqlite_pool
        
        # Use a consistent file for the duration of the test session
        # but clear it between tests (see clean_sqlite_db below)
        _SQLITE_TEST_DB = "/tmp/mayflower_pytest_shared.db"
        
        async def mocked_create_pool(*args, **kwargs):
            return await create_sqlite_pool(_SQLITE_TEST_DB)
            
        asyncpg.create_pool = mocked_create_pool
    except ImportError:
        pass

@pytest.fixture(scope="function", autouse=True)
async def clean_sqlite_db():
    """Clear the shared SQLite test database before each test if using redirection."""
    if os.environ.get("MAYFLOWER_USE_SQLITE") == "true":
        from mayflower_sandbox.db import create_sqlite_pool
        pool = await create_sqlite_pool("/tmp/mayflower_pytest_shared.db")
        async with pool.acquire() as conn:
            # We must disable FKs briefly to truncate everything or delete in order
            await conn.execute("PRAGMA foreign_keys = OFF")
            await conn.execute("DELETE FROM sandbox_filesystem")
            await conn.execute("DELETE FROM sandbox_session_bytes")
            await conn.execute("DELETE FROM sandbox_sessions")
            await conn.execute("DELETE FROM sandbox_skills")
            await conn.execute("DELETE FROM sandbox_mcp_servers")
            await conn.execute("DELETE FROM sandbox_package_cache")
            await conn.execute("PRAGMA foreign_keys = ON")
        await pool.close()
    yield


# Check if deepagents is available
DEEPAGENTS_AVAILABLE = importlib.util.find_spec("deepagents") is not None


# Mock deepagents protocol types so we can import the module for testing
@pytest.fixture(scope="session", autouse=True)
def mock_deepagents():
    """Mock deepagents module if not installed."""
    if DEEPAGENTS_AVAILABLE:
        yield
        return

    # Create mock protocol types
    mock_protocol = MagicMock()
    mock_protocol.EditResult = dict
    mock_protocol.ExecuteResponse = dict
    mock_protocol.FileDownloadResponse = dict
    mock_protocol.FileInfo = dict
    mock_protocol.FileUploadResponse = dict
    mock_protocol.GrepMatch = dict
    mock_protocol.WriteResult = dict
    mock_protocol.SandboxBackendProtocol = object

    # Patch the modules
    with patch.dict(
        sys.modules,
        {
            "deepagents": MagicMock(),
            "deepagents.backends": MagicMock(),
            "deepagents.backends.protocol": mock_protocol,
        },
    ):
        # Force reimport of our module with mocked dependencies
        if "mayflower_sandbox.deepagents_backend" in sys.modules:
            del sys.modules["mayflower_sandbox.deepagents_backend"]
        yield


# Tests assume the Dockerized database is exposed on localhost:5433.
# Allow overrides via env, but default to the container mapping.
os.environ.setdefault("POSTGRES_PORT", "5433")

# Check if Deno is available
DENO_AVAILABLE = shutil.which("deno") is not None

# Marker for tests that require Deno
requires_deno = pytest.mark.skipif(
    not DENO_AVAILABLE,
    reason="Deno is not installed (required for Pyodide sandbox execution)",
)


@pytest.fixture(scope="function", autouse=True)
async def cleanup_worker_pool():
    """Clean up worker pool and MCP bridge after each test."""
    yield
    from mayflower_sandbox.sandbox_executor import SandboxExecutor

    for _p in list(SandboxExecutor._pools.values()):
        await _p.shutdown()
    SandboxExecutor._pools.clear()

    if SandboxExecutor._mcp_bridge is not None:
        await SandboxExecutor._mcp_bridge.shutdown()
        SandboxExecutor._mcp_bridge = None
