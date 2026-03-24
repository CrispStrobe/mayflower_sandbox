"""
Mayflower Sandbox - Persistent MCP Bridge Server.

Long-running HTTP bridge server for MCP calls from Pyodide workers.
Designed to be shared across all workers in a pool for better performance.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
from typing import Any

try:
    import asyncpg
except ImportError:
    class _DummyAsyncpg:
        class UndefinedTableError(Exception): pass
        class UndefinedColumnError(Exception): pass
    asyncpg = _DummyAsyncpg()  # type: ignore

from .mcp_bindings import MCPBindingManager

logger = logging.getLogger(__name__)


class MCPBridgeServer:
    """
    Long-running HTTP bridge for MCP calls from Pyodide workers.

    This server is started once and shared across all workers in a pool.
    It handles HTTP POST /call requests and routes them to the appropriate
    MCP server via the MCPBindingManager.
    """

    def __init__(self, db_pool: Any, thread_id: str):
        """
        Initialize the MCP bridge server.

        Args:
            db_pool: PostgreSQL connection pool for loading MCP server configs
            thread_id: Thread ID for MCP session isolation
        """
        from .schema_validator import MCPSchemaValidator

        self.db_pool = db_pool
        self.thread_id = thread_id
        self._mcp_manager = MCPBindingManager()
        self._validator = MCPSchemaValidator()
        self._server: asyncio.AbstractServer | None = None
        self._port: int | None = None
        self._servers_cache: dict[str, dict[str, Any]] = {}

    @property
    def port(self) -> int | None:
        """Get the port the bridge is listening on."""
        return self._port

    @property
    def url(self) -> str | None:
        """Get the full URL of the bridge server."""
        return f"http://127.0.0.1:{self._port}" if self._port else None

    @property
    def is_running(self) -> bool:
        """Check if the bridge server is running."""
        return self._server is not None and self._server.is_serving()

    async def start(self) -> int:
        """
        Start the bridge server and return the port.

        Returns:
            The port number the server is listening on
        """
        if self.is_running:
            if self._port is None:
                raise RuntimeError("MCP bridge is running but port is not set")
            return self._port

        # Load MCP server configs from database
        self._servers_cache = await self._get_mcp_server_configs()

        # Start HTTP server on random port
        self._server = await asyncio.start_server(
            self._handle_request,
            host="127.0.0.1",
            port=0,
        )

        sock = self._server.sockets[0]
        if sock is None:
            raise RuntimeError("Server socket not available")
        self._port = sock.getsockname()[1]

        logger.info(
            f"MCP bridge started on port {self._port} for thread {self.thread_id} "
            f"with {len(self._servers_cache)} registered servers"
        )
        return self._port

    async def reload_configs(self) -> None:
        """
        Reload MCP server configs from database.

        Call this when MCP servers are added/removed via mcp_bind_http tool.
        """
        self._servers_cache = await self._get_mcp_server_configs()
        logger.info(
            f"MCP bridge configs reloaded for thread {self.thread_id}: "
            f"{list(self._servers_cache.keys())}"
        )

    async def shutdown(self) -> None:
        """Shutdown the bridge server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            self._port = None
            logger.info(f"MCP bridge stopped for thread {self.thread_id}")

    async def _get_mcp_server_configs(self) -> dict[str, dict[str, Any]]:
        """Load MCP server configurations and schemas from database."""
        async with self.db_pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    """
                    SELECT name, url, headers, auth, schemas
                    FROM sandbox_mcp_servers
                    WHERE thread_id = $1
                    """,
                    self.thread_id,
                )
            except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError, sqlite3.OperationalError) as e:
                is_missing_table = isinstance(e, asyncpg.UndefinedTableError) or (isinstance(e, sqlite3.OperationalError) and "no such table" in str(e))
                is_missing_col = isinstance(e, asyncpg.UndefinedColumnError) or (isinstance(e, sqlite3.OperationalError) and "no such column" in str(e))

                if is_missing_col and not is_missing_table:
                    # Fall back if schemas column doesn't exist yet
                    try:
                        rows = await conn.fetch(
                            """
                            SELECT name, url, headers, auth, NULL as schemas
                            FROM sandbox_mcp_servers
                            WHERE thread_id = $1
                            """,
                            self.thread_id,
                        )
                    except (asyncpg.UndefinedTableError, sqlite3.OperationalError) as e2:
                        if isinstance(e2, asyncpg.UndefinedTableError) or (isinstance(e2, sqlite3.OperationalError) and "no such table" in str(e2)):
                            rows = []
                        else:
                            raise
                elif is_missing_table:
                    logger.warning(
                        "Table 'sandbox_mcp_servers' does not exist. "
                        "MCP server bindings are unavailable. Run database migrations."
                    )
                    rows = []
                else:
                    raise

        servers: dict[str, dict[str, Any]] = {}
        for row in rows:
            raw_headers = row["headers"] or {}
            if isinstance(raw_headers, str):
                raw_headers = json.loads(raw_headers)
            raw_auth = row["auth"] or {}
            if isinstance(raw_auth, str):
                raw_auth = json.loads(raw_auth)

            # Load schemas into validator
            raw_schemas = row["schemas"] or {}
            if isinstance(raw_schemas, str):
                raw_schemas = json.loads(raw_schemas)
            if raw_schemas:
                self._validator.load_schemas(row["name"], raw_schemas)

            servers[row["name"]] = {
                "url": row["url"],
                "headers": dict(raw_headers),
                "auth": dict(raw_auth),
            }
        return servers

    @staticmethod
    def _json_default(value: Any) -> Any:
        """JSON serializer for non-standard types."""
        if isinstance(value, str | int | float | bool) or value is None:
            return value
        if isinstance(value, list | tuple | set):
            return list(value)
        if isinstance(value, dict):
            return value
        return str(value)

    async def _execute_mcp_call(
        self, server_name: str, tool_name: str, args: dict
    ) -> tuple[str, bytes]:
        """Execute an MCP call and return (status, body)."""
        if server_name not in self._servers_cache:
            raise RuntimeError(f"MCP server '{server_name}' is not registered for this thread.")

        validation_errors = self._validator.validate(server_name, tool_name, args)
        if validation_errors:
            error_list = "; ".join(validation_errors)
            return (
                "400 Bad Request",
                json.dumps(
                    {"error": f"Validation failed for {server_name}.{tool_name}: {error_list}"}
                ).encode("utf-8"),
            )

        config = self._servers_cache[server_name]
        result = await self._mcp_manager.call(
            self.thread_id,
            server_name,
            tool_name,
            args,
            url=config["url"],
            headers=config.get("headers"),
        )
        return (
            "200 OK",
            json.dumps({"result": result}, default=self._json_default).encode("utf-8"),
        )

    async def _execute_ts_eval(self, code: str, allow_net: bool | list[str] = False) -> tuple[str, bytes]:
        """Evaluate TypeScript code via Deno (Feature 8)."""
        import tempfile
        import os
        
        # Wrap code in an async IIFE so it can use top-level await/return
        # and print the result as JSON
        wrapped_code = f"""
        (async () => {{
            try {{
                const result = await (async () => {{
                    {code}
                }})();
                console.log("MAYFLOWER_JSON_START" + JSON.stringify(result) + "MAYFLOWER_JSON_END");
            }} catch (e) {{
                console.error(e);
                Deno.exit(1);
            }}
        }})();
        """
        
        fd, temp_path = tempfile.mkstemp(suffix=".ts")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(wrapped_code)
            
            cmd = ["deno", "run"]
            if allow_net is True:
                cmd.append("--allow-net")
            elif isinstance(allow_net, list):
                cmd.append(f"--allow-net={','.join(allow_net)}")
            
            cmd.append(temp_path)
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            
            stdout_str = stdout.decode(errors="replace")
            stderr_str = stderr.decode(errors="replace")
            
            # Extract JSON result if present
            result_obj = None
            if "MAYFLOWER_JSON_START" in stdout_str:
                import re
                match = re.search(r"MAYFLOWER_JSON_START(.*?)MAYFLOWER_JSON_END", stdout_str, re.DOTALL)
                if match:
                    try:
                        result_obj = json.loads(match.group(1))
                        # Clean up stdout
                        stdout_str = stdout_str.replace(match.group(0), "").strip()
                    except:
                        pass

            result = {
                "success": proc.returncode == 0,
                "stdout": stdout_str,
                "stderr": stderr_str,
                "result": result_obj
            }
            return "200 OK", json.dumps(result).encode("utf-8")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    async def _execute_cache_package(self, data: dict) -> tuple[str, bytes]:
        """Store a package wheel in the cache (Feature 1)."""
        import base64
        try:
            content = base64.b64decode(data["content_b64"])
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO sandbox_package_cache (
                        package_name, version, pyodide_version, filename, content
                    ) VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (package_name, version, pyodide_version) DO UPDATE SET
                        content = EXCLUDED.content,
                        created_at = CURRENT_TIMESTAMP
                    """,
                    data["package_name"],
                    data["version"],
                    data["pyodide_version"],
                    data["filename"],
                    content
                )
            return "200 OK", json.dumps({"success": True}).encode("utf-8")
        except Exception as e:
            return "500 Internal Server Error", json.dumps({"error": str(e)}).encode("utf-8")

    async def _execute_get_cached_package(self, data: dict) -> tuple[str, bytes]:
        """Retrieve a package wheel from the cache (Feature 1)."""
        import base64
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT content, filename FROM sandbox_package_cache
                    WHERE package_name = $1 AND version = $2 AND pyodide_version = $3
                    """,
                    data["package_name"],
                    data["version"],
                    data["pyodide_version"]
                )
                if row:
                    result = {
                        "found": True,
                        "filename": row["filename"],
                        "content_b64": base64.b64encode(row["content"]).decode("utf-8")
                    }
                else:
                    result = {"found": False}
            return "200 OK", json.dumps(result).encode("utf-8")
        except Exception as e:
            return "500 Internal Server Error", json.dumps({"error": str(e)}).encode("utf-8")

    async def _handle_request(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle HTTP request from Pyodide worker."""
        status = "200 OK"
        body = b"{}"
        try:
            # Parse HTTP request line
            request_line = await reader.readline()
            if not request_line:
                return
            parts = request_line.decode("ascii", errors="ignore").strip().split()
            if len(parts) < 3:
                raise ValueError("Malformed HTTP request line")
            method, path = parts[0], parts[1]

            # Parse headers
            headers: dict[str, str] = {}
            while True:
                line = await reader.readline()
                if not line or line == b"\r\n":
                    break
                key, _, value = line.decode("ascii", errors="ignore").partition(":")
                headers[key.strip().lower()] = value.strip()

            # Read body
            content_length = int(headers.get("content-length", "0"))
            payload = await reader.readexactly(content_length) if content_length > 0 else b""

            # Route request
            if method == "POST" and path == "/eval_ts":
                data = json.loads(payload.decode("utf-8"))
                code = data.get("code", "")
                allow_net = data.get("allow_net", False)
                status, body = await self._execute_ts_eval(code, allow_net=allow_net)
            elif method == "POST" and path == "/cache_package":
                data = json.loads(payload.decode("utf-8"))
                status, body = await self._execute_cache_package(data)
            elif method == "POST" and path == "/get_cached_package":
                data = json.loads(payload.decode("utf-8"))
                status, body = await self._execute_get_cached_package(data)
            elif method != "POST" or path != "/call":
                status = "404 Not Found"
                body = json.dumps({"error": "Endpoint not found"}).encode("utf-8")
            else:
                # Parse JSON payload and execute MCP call
                data = json.loads(payload.decode("utf-8"))
                server_name = data.get("server")
                tool_name = data.get("tool")
                if not server_name or not tool_name:
                    status = "400 Bad Request"
                    body = json.dumps({"error": "Missing 'server' or 'tool' in request"}).encode(
                        "utf-8"
                    )
                else:
                    status, body = await self._execute_mcp_call(
                        server_name, tool_name, data.get("args") or {}
                    )

        except Exception as exc:  # noqa: BLE001 - return error payload to sandbox
            logger.error("MCP bridge request failed: %s", exc, exc_info=True)
            status = "500 Internal Server Error"
            body = json.dumps({"error": str(exc)}).encode("utf-8")

        finally:
            # Send HTTP response
            writer.write(
                (
                    f"HTTP/1.1 {status}\r\n"
                    "Content-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).encode()
            )
            writer.write(body)
            await writer.drain()
            writer.close()
            await writer.wait_closed()
