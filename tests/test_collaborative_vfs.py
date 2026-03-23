import pytest
import os
import sys
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import create_sqlite_pool, MayflowerSandboxBackend, VirtualFilesystem

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "collab.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_shared_vfs_between_threads(db_pool):
    shared_vfs = "workspace_alpha"
    
    # Thread A joins workspace
    backend_a = MayflowerSandboxBackend(db_pool, "thread_a", vfs_id=shared_vfs)
    # Thread B joins same workspace
    backend_b = MayflowerSandboxBackend(db_pool, "thread_b", vfs_id=shared_vfs)
    
    # Thread A writes a file
    await backend_a.awrite("/shared.txt", "hello from a")
    
    # Thread B should see it immediately
    content = await backend_b.aread("/shared.txt")
    # Note: aread returns formatted string with line numbers in some versions, 
    # but let's check if the content is there.
    assert "hello from a" in content
    
    # Thread B modifies it (must delete first because awrite blocks overwrite)
    await backend_b.adelete("/shared.txt")
    await backend_b.awrite("/shared.txt", "updated by b")
    await asyncio.sleep(0.1)
    
    # Thread A should see the update
    content_updated = await backend_a.aread("/shared.txt")
    assert "updated by b" in content_updated

@pytest.mark.anyio
async def test_vfs_isolation_with_different_ids(db_pool):
    # Thread A in workspace 1
    backend_a = MayflowerSandboxBackend(db_pool, "thread_a", vfs_id="ws_1")
    # Thread B in workspace 2
    backend_b = MayflowerSandboxBackend(db_pool, "thread_b", vfs_id="ws_2")
    
    await backend_a.awrite("/secret.txt", "secret")
    
    # B should NOT see it
    content = await backend_b.aread("/secret.txt")
    assert "not found" in content.lower()
