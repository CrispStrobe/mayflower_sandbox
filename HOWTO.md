1. SQLite db_pool Initialization

In tests/conftest.py (lines 14-28):
- When MAYFLOWER_USE_SQLITE=true environment variable is set, the
conftest mocks asyncpg.create_pool with a custom function that calls
create_sqlite_pool
- Uses a consistent test database file:
/tmp/mayflower_pytest_shared.db
- Each test clears the database before running via the
clean_sqlite_db fixture

In src/mayflower_sandbox/db.py (line 364-366):
async def create_sqlite_pool(db_path: str) -> SqliteDatabase:
    """Create a SQLite database pool that mimics asyncpg.Pool."""
    return SqliteDatabase(db_path)
- create_sqlite_pool returns a SqliteDatabase object that mimics
asyncpg.Pool interface
- SqliteDatabase wraps sqlite3.Connection and provides async
methods: fetch(), fetchrow(), fetchval(), execute() via the
SqliteConnection wrapper

---
2. Import Path and Constructor Signature for MayflowerSandboxBackend

Import path:
from mayflower_sandbox import MayflowerSandboxBackend
# OR
from mayflower_sandbox.deepagents_backend import
MayflowerSandboxBackend

Constructor signature (lines 586-634):
def __init__(
    self,
    db_pool: Any,
    thread_id: str,
    *,
    vfs_id: str | None = None,
    allow_net: bool | list[str] = False,
    stateful: bool = True,
    enable_debugger: bool = False,
    timeout_seconds: float = 60.0,
) -> None:

Arguments:
- db_pool: asyncpg connection pool
- thread_id: Session identifier for file and execution isolation
- vfs_id: Optional shared VFS identifier (defaults to thread_id)
- allow_net: Network access control (bool or list of allowed
domains)
- stateful: Maintain state between executions (default True)
- enable_debugger: Enable Deno debugger (default False)
- timeout_seconds: Execution timeout in seconds (default 60.0)

---
3. Methods Exposed by MayflowerSandboxBackend

Inherited from PostgresBackend (file operations):
- ls_info(path: str) -> list[FileInfo] / als_info(path: str)
- read(file_path: str, offset: int = 0, limit: int = 2000, raw: bool
= False) -> str / aread(...)
- write(file_path: str, content: str) -> WriteResult / awrite(...)
- edit(file_path: str, old_string: str, new_string: str,
replace_all: bool = False) -> EditResult / aedit(...)
- delete(file_path: str) -> bool / adelete(...)
- grep_raw(pattern: str, path: str | None = None, glob: str | None =
None) -> list[GrepMatch] | str / agrep_raw(...)
- glob_info(pattern: str, path: str = "/") -> list[FileInfo] /
aglob_info(...)
- upload_files(files: list[tuple[str, bytes]]) ->
list[FileUploadResponse] / aupload_files(...)
- download_files(paths: list[str]) -> list[FileDownloadResponse] /
adownload_files(...)

Specific to MayflowerSandboxBackend (execution):
- execute(command: str) -> ExecuteResponse - Executes commands,
routes to Python (Pyodide) or Shell (BusyBox)
- aexecute(command: str) -> ExecuteResponse - Async version

Snapshot management:
- create_snapshot(ttl_days: int = 1) -> str / acreate_snapshot(...)
- restore_snapshot(snapshot_id: str) -> None /
arestore_snapshot(...)

Properties:
- id: str - Returns f"mayflower:{self._thread_id}"
- vfs_id: str - Returns the shared VFS identifier

---
4. How adownload_files Works

Location: src/mayflower_sandbox/deepagents_backend.py (lines
545-563)

async def adownload_files(self, paths: list[str]) ->
list[FileDownloadResponse]:
    responses: list[FileDownloadResponse] = []
    for path in paths:
        try:
            record = await self._vfs.read_file(path)
        except FileNotFoundError:
            responses.append(
                FileDownloadResponse(path=path, content=None,
error="file_not_found")
            )
            continue
        except InvalidPathError:
            responses.append(
                FileDownloadResponse(path=path, content=None,
error="invalid_path")
            )
            continue

        content_bytes = record.get("content", b"") or b""
        responses.append(FileDownloadResponse(path=path,
content=content_bytes, error=None))
    return responses

What it returns:
- List of FileDownloadResponse objects with fields:
    - path: str - The file path
    - content: bytes | None - File content as bytes (None if error)
    - error: str | None - Error message ("file_not_found",
"invalid_path", or None)

---
5. VFS File Listing

There is alist_files method (inherited from PostgresBackend):
- als_info(path: str) -> list[FileInfo] - Lists files/directories
under a path
- Also available as sync: ls_info(path: str) -> list[FileInfo]

The FileInfo dataclass contains:
@dataclass
class FileInfo:
    path: str = ""
    is_dir: bool = False
    size: int = 0
    modified_at: str = ""

Internal method used for listing:
- self._vfs.list_files() - Returns all files for the VFS

---
6. Usage Patterns from test_scenarios_real_world.py

Initialization:
backend = MayflowerSandboxBackend(
    db_pool,
    thread_id="agent_alpha",
    vfs_id="project_x",
    allow_net=["api.github.com"]
)

File operations:
await backend.awrite("/home/my_data.csv",
"id,name\n1,alpha\n2,beta")
read_res = await backend.aread("/home/my_data.csv")

Python execution:
destructive_code = """
import os
if os.path.exists("/home/my_data.csv"):
    os.remove("/home/my_data.csv")
"""
await backend.aexecute(destructive_code)

TypeScript execution with eval_ts:
ts_code = "return { status: 'error', reason: 'data_missing' }"
verify_res = await backend.aexecute(f"print(await
eval_ts({json.dumps(ts_code)}))")

Snapshots:
snapshot_id = await backend.acreate_snapshot(ttl_days=1)
# ... do work ...
await backend.arestore_snapshot(snapshot_id)

Shared VFS between threads:
shared_ws = "collab_env"
agent_a = MayflowerSandboxBackend(db_pool, "dev_agent",
vfs_id=shared_ws)
agent_b = MayflowerSandboxBackend(db_pool, "audit_agent",
vfs_id=shared_ws)
# Both share the same filesystem