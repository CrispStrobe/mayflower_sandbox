# Sandbox Debugging

Mayflower Sandbox supports attaching standard JavaScript and Python debuggers to the sandbox execution environment using the Chrome DevTools Protocol.

## Enabling the Debugger

To enable debugging, set `enable_debugger=True` when initializing the backend or executor.

```python
backend = MayflowerSandboxBackend(db_pool, thread_id="user_1", enable_debugger=True)
```

## How it Works

When `enable_debugger` is True, the underlying Deno worker is started with the `--inspect` flag. 

1. **Deno Level**: You can debug the worker infrastructure, VFS syncing, and the bridge itself.
2. **Pyodide Level**: You can inspect the Python interpreter's state and memory from the JS side.

## Connecting a Debugger

When you run code with the debugger enabled, Deno will print a WebSocket URL to `stderr`:

```text
Debugger listening on ws://127.0.0.1:9229/...
```

You can then:
1. Open **Chrome** and navigate to `chrome://inspect`.
2. Click "Configure..." and ensure `localhost:9229` is added.
3. Click "inspect" under the Remote Target to open the DevTools window.

## VS Code Integration

You can also use VS Code to debug:
1. Add a "Attach to Node.js/Chrome" launch configuration to your `.vscode/launch.json`.
2. Set the port to `9229`.
3. Start debugging while the sandbox is running.

> **Note**: Because Mayflower Sandbox uses a worker pool, you may need to check the logs to see which port a specific worker is using if multiple workers are in debug mode.
