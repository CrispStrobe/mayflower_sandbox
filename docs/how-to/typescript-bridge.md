# Cross-Language Eval (TypeScript Bridge)

Mayflower Sandbox allows you to execute TypeScript/JavaScript code directly from your Python sandbox. This enables agents to leverage the full power of both the Python ecosystem (Data Science, AI) and the Node/Deno ecosystem (Web scraping, Browser automation).

## Using `eval_ts`

The `eval_ts()` function is automatically injected into the built-in namespace when an MCP bridge is active.

```python
# From inside the Python sandbox
code = """
async def main():
    # Call TypeScript from Python
    res = await eval_ts("console.log('Hello from Deno'); return 1+2;")
    print(f"Result: {res['stdout']}") # Result: 3
"""
await backend.aexecute(code)
```

## Response Format

`eval_ts()` returns a dictionary with the following structure:

```json
{
  "success": true,
  "stdout": "...",
  "stderr": "",
  "error": null
}
```

## Security & Isolation

The TypeScript code is executed using **Deno's eval engine** on the host-side bridge. 

- **Permissions**: The TS code inherits the network permissions configured for the sandbox (`allow_net`).
- **Access**: The TS code has access to the Deno environment but is still isolated from your main host application process.
- **Async Support**: You can use `await` inside the TypeScript code string.

## Use Cases

1. **DOM Parsing**: Use `deno-dom` or similar libraries to parse complex HTML more efficiently than in Python.
2. **Web APIs**: Access modern web APIs that might be better supported in Deno.
3. **Multi-Step Pipelines**: Perform a calculation in Python, pass the result to a JS-based visualization library, and return the image back to Python.
