# Fine-grained Network Control

Mayflower Sandbox provides strict control over network egress from within the sandbox. By default, the sandbox is isolated from the network.

## Network Modes

You can configure network access using the `allow_net` parameter when initializing the backend or executor.

### 1. Completely Disabled (Default)
No network requests are allowed.
```python
backend = MayflowerSandboxBackend(db_pool, thread_id="user_1", allow_net=False)
```

### 2. Full Access
The sandbox can access any domain.
```python
backend = MayflowerSandboxBackend(db_pool, thread_id="user_1", allow_net=True)
```

### 3. Domain Allowlist (Recommended)
The sandbox can only access specific domains.
```python
backend = MayflowerSandboxBackend(
    db_pool, 
    thread_id="user_1", 
    allow_net=["api.github.com", "pypi.org", "files.pythonhosted.org"]
)
```

## How it Works

Mayflower Sandbox leverages **Deno's native capability security model**. When you provide an allowlist, it is passed directly to the underlying Deno process using the `--allow-net` flag.

This protection is enforced at the WebAssembly boundary. Even if a library like `requests` or `urllib` is compromised inside Pyodide, it cannot bypass the Deno runtime's host-level restrictions.

## Default Permitted Domains

When `allow_net` is enabled (even as a list), the following domains are always permitted to allow the sandbox to function correctly:
- `cdn.jsdelivr.net` (for Pyodide packages)
- `files.pythonhosted.org` (for PyPI downloads)
- `pypi.org` (for PyPI downloads)
- `127.0.0.1` (for MCP bridge communication)

## Handling Network Errors

If code inside the sandbox attempts to access a blocked domain, it will raise a `pyodide.ffi.JsException` which usually surfaces as a `NetworkError` in Python.

```python
try:
    await backend.aexecute("import requests; requests.get('https://blocked.com')")
except Exception as e:
    print(f"Request blocked: {e}")
```
