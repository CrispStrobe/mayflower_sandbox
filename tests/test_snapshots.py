import pytest
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import create_sqlite_pool, SandboxManager, VirtualFilesystem
from mayflower_sandbox.session import SessionRecovery

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "snapshots.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_create_and_restore_snapshot(db_pool):
    manager = SandboxManager(db_pool)
    vfs = VirtualFilesystem(db_pool, "test_thread")
    recovery = SessionRecovery(db_pool)
    
    # Setup original state
    await manager.get_or_create_session("test_thread", {"meta": "orig"})
    await vfs.write_file("/test.txt", b"original content")
    await recovery.save_session_bytes("test_thread", b"original state", {"vars": 1})
    
    # Create snapshot
    snap_id = await manager.create_snapshot("test_thread")
    assert snap_id.startswith("test_thread@snap_")
    
    # Modify original
    await vfs.write_file("/test.txt", b"modified content")
    await vfs.write_file("/new.txt", b"new content")
    await recovery.save_session_bytes("test_thread", b"modified state", {"vars": 2})
    
    # Restore snapshot
    restored_id = await manager.restore_snapshot(snap_id)
    assert restored_id == "test_thread"
    
    # Verify restored state
    file1 = await vfs.read_file("/test.txt")
    assert file1["content"] == b"original content"
    
    assert not await vfs.file_exists("/new.txt")
    
    state, meta = await recovery.load_session_bytes("test_thread")
    assert state == b"original state"

@pytest.mark.anyio
async def test_snapshot_cascade_delete(db_pool):
    manager = SandboxManager(db_pool)
    await manager.get_or_create_session("parent_thread")
    
    snap_id = await manager.create_snapshot("parent_thread")
    
    # Delete parent
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM sandbox_sessions WHERE thread_id = 'parent_thread'")
        
    # Verify snapshot is gone
    async with db_pool.acquire() as conn:
        snap = await conn.fetchrow("SELECT * FROM sandbox_sessions WHERE thread_id = $1", snap_id)
        assert snap is None