# VFS Snapshotting & Branching

VFS Snapshotting allows you to create point-in-time clones of your sandbox state, including all files in the virtual filesystem and the Python execution state (memory).

This is particularly useful for AI agents that need to:
- Try a complex multi-file edit or refactor safely.
- Run speculative executions.
- Roll back to a known good state if tests fail.

## Creating a Snapshot

You can create a snapshot of the current session using the `acreate_snapshot` method.

```python
# Create a snapshot that lives for 24 hours
snapshot_id = await backend.acreate_snapshot(ttl_days=1)
print(f"Created snapshot: {snapshot_id}")
```

The `snapshot_id` follows the format `{original_thread_id}@snap_{short_uuid}`.

## Restoring a Snapshot

Restoring a snapshot overwrites the current session's VFS and memory state with the state captured in the snapshot.

```python
# Roll back to a previous state
await backend.arestore_snapshot(snapshot_id)
```

## Automatic Cleanup

Snapshots are designed to be transient. They are automatically cleaned up in two ways:
1. **TTL Expiry**: Snapshots are deleted by the `CleanupJob` after their `ttl_days` expires.
2. **Parent Deletion**: If the parent session (the original `thread_id`) is deleted, all its dependent snapshots are automatically purged via database cascade constraints.

## What Is and Isn't Captured

A snapshot captures two things:

- **VFS files** — all files written to `/home`, `/tmp`, etc. via `awrite()` or by executed code.
- **Python globals** — all variables in the Pyodide execution scope, serialized with `cloudpickle`.

It does **not** capture:

- **Installed packages** — `micropip.install()` registers packages in Pyodide's module system, which lives in the worker process and is not serialized. After restoring a snapshot, any packages the original session installed must be reinstalled.

```python
# Staging: install a package and compute something
await staging.aexecute("""
    import micropip
    await micropip.install('packaging')
    from packaging.version import Version
    result = str(Version('1.2.3'))   # stored as a Python global
""")
snap = await staging.acreate_snapshot()

# Prod: restore — result variable comes back, package does not
await prod.arestore_snapshot(snap)
await prod.aexecute("""
    # 'result' is available immediately
    print(result)                    # '1.2.3'
    # 'packaging' must be reinstalled before use
    import micropip
    await micropip.install('packaging')
    from packaging.version import Version
""")
```

## Technical Details

Snapshotting uses a **Copy-on-Write** (Row Duplication) strategy in the database.
- Creating a snapshot duplicates all metadata and file content rows.
- Restoring a snapshot deletes the current session's rows and replaces them with duplicates from the snapshot.
- While this uses more storage than incremental versioning, it ensures absolute reliability and simplicity for agentic workflows.
