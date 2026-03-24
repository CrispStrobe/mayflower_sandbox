import pytest
import os
import sys
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import create_sqlite_pool, SandboxExecutor

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "debugger.db")
    pool = await create_sqlite_pool(db_path)
    # Ensure session
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO sandbox_sessions (thread_id, expires_at, vfs_id) VALUES ('debug_thread', datetime('now', '+1 day'), 'debug_thread')")
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_debugger_flag_passed_to_worker(db_pool):
    # Mock PyodideWorker to avoid starting real subprocesses
    with patch("mayflower_sandbox.worker_pool.PyodideWorker") as MockWorker:
        # Configure the mock worker instance
        mock_worker_instance = MockWorker.return_value
        mock_worker_instance.start = AsyncMock()
        mock_worker_instance.shutdown = AsyncMock()
        
        executor = SandboxExecutor(db_pool, "debug_thread", enable_debugger=True)
        
        # Reset any existing pools
        SandboxExecutor._pools.clear()

        # Trigger pool creation
        await executor._ensure_pool(enable_debugger=True)
        
        # Verify PyodideWorker was initialized with enable_debugger=True
        # Check constructor calls
        found_debug_init = False
        for call in MockWorker.call_args_list:
            if call.kwargs.get("enable_debugger") is True:
                found_debug_init = True
                break
        
        assert found_debug_init, "PyodideWorker should be initialized with enable_debugger=True"

@pytest.mark.anyio
async def test_debugger_flag_in_backend(db_pool):
    from mayflower_sandbox import MayflowerSandboxBackend
    backend = MayflowerSandboxBackend(db_pool, "debug_thread", enable_debugger=True)
    assert backend._executor.enable_debugger is True
