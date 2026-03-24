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
    db_path = str(tmp_path / "advanced_scenarios.db")
    pool = await create_sqlite_pool(db_path)
    yield pool
    await pool.close()

@pytest.mark.anyio
async def test_data_science_caching_rollback_scenario(db_pool, monkeypatch):
    """
    Scenario 1: Data Science Pipeline with Library Caching & Rollback
    1. Agent installs PyYAML (triggers caching logic).
    2. Agent creates a data processing pipeline and a config file.
    3. Agent takes a snapshot.
    4. Agent 'breaks' the pipeline by deleting the config and corrupting the script.
    5. Agent restores the snapshot.
    6. Agent verifies PyYAML is still available and the config is back.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    backend = MayflowerSandboxBackend(db_pool, "ds_agent", stateful=True)

    # 1 & 2. Install and Setup Pipeline
    # Enable network for initial install
    # Use a unique thread ID to avoid pool reuse issues
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
    print(f"SETUP OUTPUT: {res.output}")
    assert res.exit_code == 0
    assert "PACKAGING_OK" in res.output
    
    await backend.awrite("/home/config.yaml", "threshold: 0.5\nmode: strict")

    # 3. Snapshot
    snapshot_id = await backend.acreate_snapshot()

    # 4. Break Environment
    break_code = """
import os
os.remove('/home/config.yaml')
status = 'BROKEN'
print("Pipeline destroyed")
"""
    await backend.aexecute(break_code)
    assert "not found" in (await backend.aread("/home/config.yaml")).lower()

    # 5. Restore
    await backend.arestore_snapshot(snapshot_id)

    # 6. Verify
    # VFS check
    assert await backend._vfs.file_exists("/home/config.yaml")
    
    # Memory and Library check
    verify_code = """
import packaging
print(f"Status: {status}")
print(f"Library: {packaging.__name__}")
"""
    res = await backend.aexecute(verify_code)
    assert "Status: initialized" in res.output
    assert "Library: packaging" in res.output

@pytest.mark.anyio
async def test_collaborative_doc_gen_scenario(db_pool, monkeypatch):
    """
    Scenario 2: Multi-Agent Collaborative Documentation
    1. Writer Agent creates a shared workspace 'docs_ws' and writes Markdown.
    2. Formatter Agent (different thread) joins same workspace.
    3. Formatter Agent reads Markdown and 'generates' a table of contents.
    4. Writer Agent verifies it can see the changes made by Formatter.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    shared_ws = "docs_ws"
    
    writer = MayflowerSandboxBackend(db_pool, "writer_thread", vfs_id=shared_ws)
    formatter = MayflowerSandboxBackend(db_pool, "formatter_thread", vfs_id=shared_ws)

    # 1. Writer creates initial doc
    await writer.awrite("/home/README.md", "# Project\n\n## Introduction\nContent here.")

    # 2. Formatter sees it and adds TOC
    doc_content = await formatter.aread("/home/README.md")
    assert "# Project" in doc_content
    
    # Simple Python logic to prepend TOC
    toc_code = """
with open('/home/README.md', 'r') as f:
    lines = f.readlines()
with open('/home/README.md', 'w') as f:
    f.write("# TOC\\n- [Intro](#intro)\\n\\n")
    f.writelines(lines)
print("TOC Generated")
"""
    await formatter.aexecute(toc_code)

    # 3. Writer verifies result
    final_doc = await writer.aread("/home/README.md")
    assert "# TOC" in final_doc
    assert "## Introduction" in final_doc

@pytest.mark.anyio
async def test_secure_ts_data_fetch_scenario(db_pool, monkeypatch):
    """
    Scenario 3: Secure Web Data Fetch via TS Bridge
    1. Agent needs to fetch data from GitHub API.
    2. Agent is restricted to only 'api.github.com'.
    3. Agent uses eval_ts to perform the fetch (JS fetch is often easier for agents).
    4. Agent processes the data in Python.
    5. Agent tries to hit unauthorized site and is blocked.
    """
    if not shutil.which("deno"):
        pytest.skip("Deno not found")

    monkeypatch.setenv("PYODIDE_POOL_SIZE", "1")
    # Whitelist only GitHub
    backend = MayflowerSandboxBackend(
        db_pool, 
        "web_agent", 
        allow_net=["api.github.com"]
    )

    # 1. Successful TS Fetch from allowed domain
    # We simulate a real call. Deno's --allow-net will enforce this.
    # We use a public API endpoint.
    ts_fetch_code = """
    const resp = await fetch('https://api.github.com/zen');
    return { ok: resp.ok, text: await resp.text() };
    """
    
    # We need to register a dummy server to ensure bridge is active for eval_ts
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO sandbox_mcp_servers (thread_id, name, url, vfs_id) VALUES ($1, $2, $3, $4)", 
                           "web_agent", "dummy", "http://localhost", "web_agent")

    py_code = f"print(await eval_ts({json.dumps(ts_fetch_code)}))"
    res = await backend.aexecute(py_code)
    
    assert "'ok': True" in res.output or "'result': {'ok': True}" in res.output
    # GitHub Zen API returns a random string
    assert len(res.output) > 20

    # 2. Blocked Fetch from forbidden domain
    ts_forbidden = "return await fetch('https://google.com').then(r => r.status)"
    forbidden_py = f"print(await eval_ts({json.dumps(ts_forbidden)}))"
    res_blocked = await backend.aexecute(forbidden_py)
    
    # Deno will throw a PermissionDenied or NotCapable error
    assert "PermissionDenied" in res_blocked.output or "NetworkError" in res_blocked.output or "NotCapable" in res_blocked.output
    assert "google.com" in res_blocked.output
