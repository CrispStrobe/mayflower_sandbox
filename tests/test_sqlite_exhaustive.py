import asyncio
import json
import pytest
import shutil
from datetime import datetime, timedelta
from mayflower_sandbox import (
    create_sqlite_pool, 
    SandboxManager, 
    VirtualFilesystem, 
    SandboxExecutor
)
from mayflower_sandbox.session import SessionRecovery, StatefulExecutor
from mayflower_sandbox.manager import SessionExpiredError, SessionNotFoundError

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "exhaustive.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_manager_exhaustive(db_pool):
    manager = SandboxManager(db_pool)
    tid = "test_manager"
    
    # get_or_create_session (new)
    s1 = await manager.get_or_create_session(tid, {"key": "val"})
    assert s1["thread_id"] == tid
    
    # SQLite returns string for JSON columns in this implementation
    meta = s1["metadata"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta == {"key": "val"}
    
    # get_or_create_session (existing)
    s2 = await manager.get_or_create_session(tid)
    assert s1["created_at"] == s2["created_at"]
    
    # update_last_accessed
    old_ts = s2["last_accessed"]
    await asyncio.sleep(0.1)
    await manager.update_last_accessed(tid)
    s3 = await manager.get_session(tid)
    assert s3["last_accessed"] >= old_ts
    
    # list_active_sessions
    await manager.get_or_create_session("other_tid")
    sessions = await manager.list_active_sessions(limit=10)
    assert len(sessions) >= 2
    
    # cleanup_expired_sessions
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO sandbox_sessions (thread_id, expires_at) VALUES ($1, $2)",
            "exp", datetime.now() - timedelta(days=1)
        )
    deleted = await manager.cleanup_expired_sessions()
    assert deleted >= 1
    with pytest.raises(SessionNotFoundError):
        await manager.get_session("exp")

@pytest.mark.anyio
async def test_vfs_exhaustive(db_pool):
    tid = "test_vfs"
    vfs = VirtualFilesystem(db_pool, tid)
    
    # write_file & MIME detection
    await vfs.write_file("/test.png", b"\x89PNG\r\n\x1a\n")
    f = await vfs.read_file("/test.png")
    assert f["content_type"] == "image/png"
    
    # overwrite
    await vfs.write_file("/test.png", b"new content")
    f = await vfs.read_file("/test.png")
    assert f["content"] == b"new content"
    
    # list_files with pattern
    await vfs.write_file("/data/1.txt", b"1")
    await vfs.write_file("/data/2.txt", b"2")
    await vfs.write_file("/other.txt", b"3")
    
    all_files = await vfs.list_files()
    assert len(all_files) == 4 # /test.png + 3 others
    
    data_files = await vfs.list_files(pattern="/data/%")
    assert len(data_files) == 2
    
    # file_exists
    assert await vfs.file_exists("/test.png")
    assert not await vfs.file_exists("/ghost")
    
    # get_all_files_for_pyodide
    py_files = await vfs.get_all_files_for_pyodide()
    assert "/test.png" in py_files
    assert py_files["/data/1.txt"] == b"1"

@pytest.mark.anyio
async def test_session_recovery_exhaustive(db_pool):
    manager = SandboxManager(db_pool)
    recovery = SessionRecovery(db_pool)
    tid = "test_recovery"
    
    # Must create session first due to FK
    await manager.get_or_create_session(tid)
    
    # Save
    await recovery.save_session_bytes(tid, b"state123", {"meta": "data"})
    
    # Load
    content, meta = await recovery.load_session_bytes(tid)
    assert content == b"state123"
    assert meta == {"meta": "data"}
    
    # Update
    await recovery.save_session_bytes(tid, b"state456", {"meta": "updated"})
    content, meta = await recovery.load_session_bytes(tid)
    assert content == b"state456"
    assert meta == {"meta": "updated"}
    
    # Delete
    assert await recovery.delete_session_bytes(tid)
    content, _ = await recovery.load_session_bytes(tid)
    assert content is None

@pytest.mark.anyio
async def test_stateful_executor_db_ops(db_pool):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")
        
    tid = "test_stateful"
    executor = StatefulExecutor(db_pool, tid)
    
    # Run 1: Set variable
    await executor.execute("x = 100")
    
    # Run 2: Verify variable persisted (DB save/load check)
    result = await executor.execute("print(x)")
    assert "100" in result.stdout
    
    # Reset
    await executor.reset_session()
    result = await executor.execute("print(x)")
    # x should be gone, so print(x) should fail
    assert not result.success

@pytest.mark.anyio
async def test_mcp_config_db_ops(db_pool):
    tid = "test_mcp"
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO sandbox_mcp_servers (thread_id, name, url, headers, auth, schemas)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, tid, "my-server", "http://localhost:8000", '{"h": "1"}', '{"a": "1"}', '{"tool": {}}')
    
    executor = SandboxExecutor(db_pool, tid)
    configs = await executor._get_mcp_server_configs()
    
    assert "my-server" in configs
    assert configs["my-server"]["url"] == "http://localhost:8000"
    assert configs["my-server"]["headers"] == {"h": "1"}
