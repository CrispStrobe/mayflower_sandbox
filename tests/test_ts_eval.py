import pytest
import os
import sys
import asyncio
import shutil

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import create_sqlite_pool, MayflowerSandboxBackend

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "ts_eval.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_ts_eval_integration(db_pool):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")
        
    backend = MayflowerSandboxBackend(db_pool, "ts_thread")
    
    # We need to register at least one MCP server to trigger bridge start,
    # or we could force the bridge to start some other way.
    # Currently _execute_with_pool only starts bridge if bridge_port is returned.
    # bridge_port is returned only if _ensure_mcp_bridge finds servers.
    
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO sandbox_mcp_servers (thread_id, name, url)
            VALUES ('ts_thread', 'dummy', 'http://localhost:8080')
        """)
        
    # Python code calling TS
    code = """
import json
res = await eval_ts("console.log(1+2)")
print(f"TS_RESULT: {res['stdout'].strip()}")
"""
    result = await backend.aexecute(code)
    assert result.exit_code == 0
    assert "TS_RESULT: 3" in result.output
    
    # Test TS error
    code_err = """
res = await eval_ts("throw new Error('ts_boom')")
print(f"TS_SUCCESS: {res['success']}")
"""
    result_err = await backend.aexecute(code_err)
    assert result_err.exit_code == 0
    assert "TS_SUCCESS: False" in result_err.output
