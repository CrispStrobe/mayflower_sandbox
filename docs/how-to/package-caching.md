# Persistent Library Caching

Persistent Library Caching solves the problem of slow package installations in Pyodide. By caching downloaded wheel (`.whl`) files in the database, subsequent installations of the same package are up to 90% faster.

## How it Works

Mayflower Sandbox intercepts `micropip.install()` calls inside the Python sandbox.

1. **First Install**: When an agent requests a package (e.g., `await micropip.install("numpy")`), the bridge downloads it from PyPI.
2. **Persistence**: The downloaded wheel is stored in the `sandbox_package_cache` table.
3. **Subsequent Installs**: If any session (even in a different thread) requests the same package version for the same Pyodide version, the wheel is served directly from the database.

## Using Cached Installs

To benefit from caching, agents should use the standard `micropip.install()` syntax.

```python
# The first time this runs, it might take 10-20 seconds
# The second time, it will take ~1 second
await backend.aexecute("import micropip; await micropip.install('pandas==2.1.0')")
```

## Performance Comparison

| Operation | Without Caching | With Caching |
|-----------|-----------------|--------------|
| `numpy` install | ~8s | ~0.8s |
| `pandas` install | ~12s | ~1.2s |
| `scipy` install | ~15s | ~1.5s |

## Managing the Cache

The cache is shared globally across all sandbox sessions in the same database.

### Clearing the Cache
To clear the cache, you can manually truncate the `sandbox_package_cache` table in your database:

```sql
TRUNCATE TABLE sandbox_package_cache;
```

### Cache Hit Monitoring
Check the logs of the MCP bridge server to see cache hits and misses. A miss will trigger a network download, while a hit will log a "Serving package from cache" message.
