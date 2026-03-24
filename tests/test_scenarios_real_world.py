import pytest
import os
import sys
import asyncio
import json
import shutil
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mayflower_sandbox import create_sqlite_pool, MayflowerSandboxBackend

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def db_pool(tmp_path):
    db_path = str(tmp_path / "scenarios.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_complex_agent_workflow_scenario(db_pool, monkeypatch):
    """
    Scenario: An AI agent is tasked with refactoring a data processing pipeline.
    1. Setup: Workspace 'project_x', initial data files.
    2. Snapshot: Capture 'known_good' state.
    3. Experiment: Perform a 'destructive' refactor (delete files, change state).
    4. Validate: Use eval_ts to check data integrity.
    5. Revert: Roll back to 'known_good' state.
    6. Network: Verify it can't exfiltrate data during the process.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    # Force pool size 1 for memory persistence check
    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    # 1. SETUP
    # Initialize agent with shared workspace and network restriction
    backend = MayflowerSandboxBackend(
        db_pool, 
        thread_id="agent_alpha", 
        vfs_id="project_x",
        allow_net=["api.github.com"] # Only allow specific domain
    )
    # Write initial data and script
    await backend.awrite("/home/my_data.csv", "id,name\n1,alpha\n2,beta")
    await backend.awrite("/home/my_script.py", "x = 10\nprint('Initial state ready')")
    
    # Run to set initial memory state (x=10)
    res = await backend.aexecute("python /home/my_script.py")
    assert res.exit_code == 0
    
    # 2. SNAPSHOT
    # Save the 'known_good' state
    snapshot_id = await backend.acreate_snapshot(ttl_days=1)
    
    # The agent "mistakenly" deletes data and corrupts state
    destructive_code = """
import os
if os.path.exists("/home/my_data.csv"):
    os.remove("/home/my_data.csv")
    print("REMOVED /home/my_data.csv")
x = 999
print(f"State corrupted: x={x}")
"""
    res = await backend.aexecute(destructive_code)
    assert res.exit_code == 0
    
    # Verify files are gone and state is changed
    read_res = await backend.aread("/home/my_data.csv")
    assert "not found" in read_res.lower()
    res = await backend.aexecute("print(f'Current x: {x}')")
    assert "Current x: 999" in res.output
    
    # 4. CROSS-LANGUAGE TASK
    # Use eval_ts to generate a verification report (Feature 8)
    ts_code = "return { timestamp: new Date().toISOString(), status: 'error', reason: 'data_missing' }"
    verify_res = await backend.aexecute(f"print(await eval_ts({json.dumps(ts_code)}))")
    assert "data_missing" in verify_res.output
    
    # 5. REVERT
    # Realize the mistake and restore the snapshot
    await backend.arestore_snapshot(snapshot_id)
    
    # Verify VFS is restored (check DB directly via VFS instance)
    assert await backend._vfs.file_exists("/home/my_data.csv")
    
    # Verify Memory is restored (x should be 10 again)
    res_restored = await backend.aexecute("print(f'Restored x: {x}')")
    assert "Restored x: 10" in res_restored.output
    
    res_files = await backend.aexecute("import os; print(f'RESTORED FILES: {os.listdir(\"/home\")}')")
    assert "my_data.csv" in res_files.output
    
    # 6. NETWORK SECURITY
    # Ensure agent can't hit malicious site during refactor
    net_res = await backend.aexecute("python -c \"import urllib.request; urllib.request.urlopen('https://google.com')\"")
    # Should fail because only github was whitelisted
    assert net_res.exit_code != 0
    assert "PermissionDenied" in net_res.output or "NetworkError" in net_res.output or "error" in net_res.output.lower()

@pytest.mark.anyio
async def test_collaborative_debugging_scenario(db_pool):
    """
    Scenario: Multi-agent collaboration with debugger.
    1. Agent A writes code to a shared workspace.
    2. Agent B (Debugger Agent) joins and inspects the workspace.
    3. They use eval_ts to share complex JS-based validation logic.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    shared_ws = "collab_env"
    
    # Agent A: The Developer
    agent_a = MayflowerSandboxBackend(db_pool, "dev_agent", vfs_id=shared_ws)
    await agent_a.awrite("/app.py", "def run(): return 'running'")
    
    # Agent B: The Auditor
    # Starts with debugger enabled (Feature 6)
    agent_b = MayflowerSandboxBackend(db_pool, "audit_agent", vfs_id=shared_ws, enable_debugger=True)
    
    # Agent B can see Agent A's code
    code_b = await agent_b.aread("/app.py")
    assert "def run" in code_b
    
    # They both use eval_ts to check Deno version consistency
    ts_check = "return Deno.version.deno"
    res_a = await agent_a.aexecute(f"print(await eval_ts({json.dumps(ts_check)}))")
    res_b = await agent_b.aexecute(f"print(await eval_ts({json.dumps(ts_check)}))")
    
    assert res_a.output.strip() == res_b.output.strip()
