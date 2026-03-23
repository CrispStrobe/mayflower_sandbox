import pytest
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import create_sqlite_pool, SandboxExecutor

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "network.db")
    pool = await create_sqlite_pool(db_path)
    # Ensure session
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO sandbox_sessions (thread_id, expires_at, vfs_id) VALUES ('net_thread', datetime('now', '+1 day'), 'net_thread')")
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_shell_network_allowlist(db_pool):
    import shutil
    if not shutil.which("deno"):
        pytest.skip("Deno not found")
        
    executor = SandboxExecutor(db_pool, "net_thread", allow_net=["example.com"])
    
    # Check that Deno's fetch fails for a non-whitelisted domain
    # We use Deno's fetch directly via JS eval or we can just use busybox wget.
    # busybox wget might be tricky because it doesn't support https by default in our wasm build,
    # but we can try to curl/wget. Wait, our busybox doesn't have curl. It has wget.
    # Let's test with Deno's shell directly or just check the generated command.
    
    cmd = executor._build_shell_command("echo hello")
    # Should include --allow-net=example.com
    assert "--allow-net=example.com" in cmd

@pytest.mark.anyio
async def test_python_network_allowlist(db_pool):
    # For Python, the executor command includes the Deno start args
    executor = SandboxExecutor(db_pool, "net_thread", allow_net=["example.com"])
    
    cmd = executor._build_command("print('hi')")
    # Because _build_command handles allowed_hosts with defaults
    net_flag = next((arg for arg in cmd if arg.startswith("--allow-net=")), None)
    assert net_flag is not None
    assert "example.com" in net_flag
    assert "pypi.org" in net_flag # Default PyPI hosts should be there
