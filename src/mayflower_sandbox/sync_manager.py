"""
SyncSandboxManager — thread-safe synchronous bridge for MayflowerSandboxBackend.

Owns a single persistent asyncio event loop running in a background daemon thread.
All sandbox operations are submitted via asyncio.run_coroutine_threadsafe(), which:
  - Avoids spawning a new OS thread + event loop per call (the old approach)
  - Keeps the aiosqlite / asyncio.to_thread pool alive and properly associated
    with one loop for the entire process lifetime
  - Serialises DB writes through the single loop while the Pyodide WorkerPool
    handles execution concurrency (controlled by PYODIDE_POOL_SIZE, default 3)

Usage (call once at startup, reuse the singleton):

    from mayflower_sandbox.sync_manager import SyncSandboxManager
    manager = SyncSandboxManager("/path/to/sandbox_vfs.db")

    stdout, stderr, exit_code = manager.execute("print(2+2)", thread_id="user_1")
    stdout, stderr, exit_code = manager.execute("ls /home", thread_id="user_1", is_shell=True)
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class SyncSandboxManager:
    """Thread-safe synchronous wrapper around MayflowerSandboxBackend.

    One instance should be created at application startup and reused for the
    lifetime of the process.  Multiple threads may call ``execute()`` concurrently;
    requests are dispatched through a single persistent asyncio event loop.
    """

    def __init__(
        self,
        db_path: str,
        allow_net: bool = False,
        timeout_seconds: float = 60.0,
    ) -> None:
        """Create the manager and start the background event loop.

        Args:
            db_path: Path to the sandbox SQLite database file.
            allow_net: Whether sandbox code may make network calls (default False).
            timeout_seconds: Default execution timeout per call.
        """
        self._db_path = db_path
        self._allow_net = allow_net
        self._timeout_seconds = timeout_seconds
        self._pool: object = None

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="sandbox-event-loop",
        )
        self._thread.start()

        # Initialise the SQLite pool inside the persistent loop
        future = asyncio.run_coroutine_threadsafe(self._init_pool(), self._loop)
        future.result(timeout=30)
        logger.info(f"SyncSandboxManager ready (db={db_path!r})")

    # ------------------------------------------------------------------
    # Internal loop management
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _init_pool(self) -> None:
        from .db import create_sqlite_pool  # local import — optional dep
        self._pool = await create_sqlite_pool(self._db_path)

    # ------------------------------------------------------------------
    # Public sync API
    # ------------------------------------------------------------------

    def execute(
        self,
        code: str,
        thread_id: str,
        timeout: float | None = None,
        is_shell: bool = False,
    ) -> tuple[str, str, int]:
        """Execute code synchronously. Safe to call from any thread.

        Args:
            code: Python code or shell command to run.
            thread_id: Per-user isolation key (e.g. ``"user_42"``).
            timeout: Execution timeout in seconds; falls back to the constructor default.
            is_shell: If True, run as BusyBox shell command instead of Python.

        Returns:
            Tuple of (stdout, stderr, exit_code).
        """
        t = timeout if timeout is not None else self._timeout_seconds
        future = asyncio.run_coroutine_threadsafe(
            self._aexecute(code, thread_id, t, is_shell),
            self._loop,
        )
        try:
            return future.result(timeout=t + 10)
        except TimeoutError:
            future.cancel()
            return "", f"Timeout nach {t:.0f}s", -1
        except Exception as exc:
            return "", f"Sandbox-Fehler: {exc}", 1

    # ------------------------------------------------------------------
    # Async implementation (runs inside the persistent loop)
    # ------------------------------------------------------------------

    async def _aexecute(
        self,
        code: str,
        thread_id: str,
        timeout: float,
        is_shell: bool,
    ) -> tuple[str, str, int]:
        from .deepagents_backend import MayflowerSandboxBackend  # local import

        backend = MayflowerSandboxBackend(
            self._pool,
            thread_id=thread_id,
            allow_net=self._allow_net,
            stateful=True,
            timeout_seconds=timeout,
        )
        if is_shell:
            res = await backend._executor.execute_shell(code)
        else:
            res = await backend._executor.execute(code)

        stdout = (getattr(res, "stdout", None) or "")[:4000]
        stderr = (getattr(res, "stderr", None) or "")[:1000]
        exit_code = getattr(res, "exit_code", None)
        if exit_code is None:
            exit_code = 0 if getattr(res, "success", True) else 1
        return stdout, stderr, exit_code

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Gracefully stop the background event loop."""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        logger.info("SyncSandboxManager shut down")
