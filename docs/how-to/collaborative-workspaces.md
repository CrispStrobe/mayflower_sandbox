# Collaborative VFS Workspaces

Collaborative VFS allows multiple sandbox sessions (different `thread_id`s) to share the same persistent storage workspace. This is essential for multi-agent collaboration where different agents need to work on the same set of files simultaneously.

## How it Works

The virtual filesystem is decoupled from the session identifier (`thread_id`) via a separate `vfs_id`.

- By default, `vfs_id` is equal to `thread_id`, providing complete isolation.
- By providing a custom `vfs_id`, you can group multiple sessions into one storage pool.

## Using a Shared Workspace

To have two different agents share a workspace, initialize them with the same `vfs_id`.

```python
# Agent 1 (e.g. a Frontend Developer)
agent_1 = MayflowerSandboxBackend(db_pool, thread_id="dev_1", vfs_id="project_alpha")

# Agent 2 (e.g. a Backend Developer)
agent_2 = MayflowerSandboxBackend(db_pool, thread_id="dev_2", vfs_id="project_alpha")

# Agent 1 writes a file
await agent_1.awrite("/index.html", "<html>...</html>")

# Agent 2 can immediately read it
content = await agent_2.aread("/index.html")
print(content)
```

## Benefits

1. **Multi-Agent Coordination**: Agents can exchange data through the filesystem.
2. **Specialized Roles**: One agent can generate data (e.g. a scraper) while another analyzes it (e.g. a data scientist) using the same workspace.
3. **Session Resumption**: You can spawn a new thread to "inspect" an existing workspace without affecting the original thread's memory state.

## Conflict Resolution

Mayflower Sandbox uses **Last-Write-Wins** at the database level for shared workspaces. If two agents write to the same file path simultaneously, the database transaction that completes last will persist. 

For high-concurrency collaborative editing, it is recommended to have agents work in different directories within the shared workspace.
