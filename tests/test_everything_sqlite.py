import asyncio
import os
import sys
import json
import shutil
import pytest
from datetime import datetime, timedelta
from typing import Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import (
    create_sqlite_pool,
    SandboxManager,
    VirtualFilesystem,
    SandboxExecutor,
)
from mayflower_sandbox.cleanup import CleanupJob
from mayflower_sandbox.session import SessionRecovery, StatefulExecutor
from mayflower_sandbox.manager import SessionExpiredError, SessionNotFoundError
from mayflower_sandbox.filesystem import FileTooLargeError, InvalidPathError, FileNotFoundError as VFSFileNotFoundError

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    """Create test SQLite database connection pool."""
    db_path = str(tmp_path / "everything.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

# -------------------------------------------------------------------------
# Manager Tests (adapted from test_manager.py)
# -------------------------------------------------------------------------

@pytest.mark.anyio
async def test_manager_lifecycle(db_pool):
    manager = SandboxManager(db_pool)
    tid = "mgr_test"
    
    # Create
    session = await manager.get_or_create_session(tid, {"user": "alice"})
    assert session["thread_id"] == tid
    
    # Fetch
    fetched = await manager.get_session(tid)
    assert fetched["thread_id"] == tid
    
    # Update
    old_accessed = fetched["last_accessed"]
    await asyncio.sleep(0.1)
    await manager.update_last_accessed(tid)
    updated = await manager.get_session(tid)
    assert updated["last_accessed"] >= old_accessed
    
    # Expiration
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE sandbox_sessions SET expires_at = $1 WHERE thread_id = $2",
            datetime.now() - timedelta(days=1), tid
        )
    
    with pytest.raises(SessionExpiredError):
        await manager.get_session(tid)

# -------------------------------------------------------------------------
# Filesystem Tests (adapted from test_filesystem.py)
# -------------------------------------------------------------------------

@pytest.mark.anyio
async def test_vfs_ops(db_pool):
    tid = "vfs_test"
    # Ensure session exists
    manager = SandboxManager(db_pool)
    await manager.get_or_create_session(tid)
    
    vfs = VirtualFilesystem(db_pool, tid)
    
    # Write/Read
    content = b"vfs data"
    await vfs.write_file("/test.txt", content)
    res = await vfs.read_file("/test.txt")
    assert res["content"] == content
    assert res["content_type"] == "text/plain"
    
    # Binary
    png = b"\x89PNG\r\n\x1a\n"
    await vfs.write_file("/img.png", png)
    res = await vfs.read_file("/img.png")
    assert res["content_type"] == "image/png"
    
    # List
    files = await vfs.list_files()
    assert len(files) == 2
    
    # Isolation
    vfs2 = VirtualFilesystem(db_pool, "other_thread")
    await manager.get_or_create_session("other_thread")
    assert not await vfs2.file_exists("/test.txt")

# -------------------------------------------------------------------------
# Cleanup Tests (adapted from test_cleanup.py)
# -------------------------------------------------------------------------

@pytest.mark.anyio
async def test_cleanup_ops(db_pool):
    job = CleanupJob(db_pool, interval_seconds=1)
    
    # Create expired session with files
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sandbox_sessions (thread_id, expires_at) VALUES ($1, $2)",
            "expired_tid", datetime.now() - timedelta(days=1)
        )
    
    vfs = VirtualFilesystem(db_pool, "expired_tid")
    await vfs.write_file("/junk.txt", b"junk")
    
    # Run cleanup
    stats = await job.cleanup_expired_sessions()
    assert stats["sessions_deleted"] == 1
    assert stats["files_deleted"] == 1
    
    # Verify gone
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sandbox_sessions WHERE thread_id = 'expired_tid'")
        assert row is None

# -------------------------------------------------------------------------
# Session Recovery Tests (adapted from test_session_recovery.py)
# -------------------------------------------------------------------------

@pytest.mark.anyio
async def test_recovery_ops(db_pool):
    recovery = SessionRecovery(db_pool)
    tid = "rec_test"
    await SandboxManager(db_pool).get_or_create_session(tid)
    
    state = b"pyodide_state_bytes"
    meta = {"vars": ["a", "b"]}
    
    await recovery.save_session_bytes(tid, state, meta)
    
    s, m = await recovery.load_session_bytes(tid)
    assert s == state
    # Handle SQLite JSON string if necessary, but SessionRecovery.load_session_bytes 
    # should ideally handle it. Let's see what it returns.
    if isinstance(m, str):
        m = json.loads(m)
    assert m == meta

# -------------------------------------------------------------------------
# MCP Config Tests
# -------------------------------------------------------------------------

@pytest.mark.anyio
async def test_mcp_configs(db_pool):
    tid = "mcp_test"
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO sandbox_mcp_servers (thread_id, name, url, headers, auth, schemas)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, tid, "srv", "http://srv", '{"h":1}', '{"a":1}', '{"s":1}')
        
    executor = SandboxExecutor(db_pool, tid)
    configs = await executor._get_mcp_server_configs()
    assert "srv" in configs
    assert configs["srv"]["url"] == "http://srv"

# -------------------------------------------------------------------------
# Stateful Executor (Full Integration)
# -------------------------------------------------------------------------

@pytest.mark.anyio
async def test_stateful_integration(db_pool):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")
        
    tid = "stateful_integration"
    executor = StatefulExecutor(db_pool, tid)
    
    await executor.execute("a = 42")
    res = await executor.execute("print(a)")
    assert "42" in res.stdout
    
    # Verify it's actually in DB
    recovery = SessionRecovery(db_pool)
    state, _ = await recovery.load_session_bytes(tid)
    assert state is not None
    assert len(state) > 0
