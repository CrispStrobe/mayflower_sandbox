"""
SyncSandboxManager — thread-safe synchronous bridge for MayflowerSandboxBackend.

Design
------
Owns a single persistent asyncio event loop running in a background daemon thread.
All sandbox operations are submitted via asyncio.run_coroutine_threadsafe(), which:

  - Avoids spawning a new OS thread + event loop per call
  - Keeps the SqliteDatabase pool (asyncio.to_thread-based) in one stable loop
  - Lets the Pyodide WorkerPool manage execution concurrency (PYODIDE_POOL_SIZE)

Uses the public DeepAgents SandboxBackendProtocol API (aexecute with sentinels,
als_info, adownload_files) — not private _executor attributes.

Routing sentinels
-----------------
  "__PYTHON__\\n<code>"   → Pyodide WASM
  "__SHELL__\\n<command>" → BusyBox WASM

Usage (call once at startup, reuse the singleton)::

    from mayflower_sandbox.sync_manager import SyncSandboxManager
    manager = SyncSandboxManager("/path/to/sandbox_vfs.db")

    output, exit_code = manager.execute("print(2+2)", thread_id="user_1")
    output, exit_code = manager.execute("ls /home", thread_id="user_1", is_shell=True)
    files = manager.list_files(thread_id="user_1", path="/home")
    content = manager.download_file(thread_id="user_1", path="/home/plot.png")
"""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .deepagents_backend import FileInfo

logger = logging.getLogger(__name__)

_PYTHON_SENTINEL = "__PYTHON__"
_SHELL_SENTINEL = "__SHELL__"


class SyncSandboxManager:
    """Thread-safe synchronous wrapper around MayflowerSandboxBackend.

    One instance should be created at application startup and reused for the
    lifetime of the process.  Multiple threads may call ``execute()``
    concurrently; requests are dispatched through the single persistent loop.
    """

    # Packages that are bundled with Pyodide but not auto-loaded.
    # Installed once per thread_id on first use; persisted in the thread's VFS.
    DEFAULT_PREINSTALL: tuple[str, ...] = (
        "numpy", "matplotlib", "pandas", "scipy", "pillow",
    )

    def __init__(
        self,
        db_path: str,
        allow_net: bool = False,
        timeout_seconds: float = 60.0,
        preinstall: tuple[str, ...] | None = None,
    ) -> None:
        self._db_path = db_path
        self._allow_net = allow_net
        self._timeout_seconds = timeout_seconds
        self._pool: object = None
        self._preinstall: tuple[str, ...] = (
            preinstall if preinstall is not None else self.DEFAULT_PREINSTALL
        )
        self._warmed_threads: set[str] = set()
        self._warm_lock: asyncio.Lock | None = None  # created inside the loop

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="sandbox-event-loop",
        )
        self._thread.start()

        future = asyncio.run_coroutine_threadsafe(self._init_pool(), self._loop)
        future.result(timeout=30)
        logger.info("SyncSandboxManager ready (db=%r)", db_path)

    # ------------------------------------------------------------------
    # Internal loop management
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _init_pool(self) -> None:
        from .db import create_sqlite_pool
        self._pool = await create_sqlite_pool(self._db_path)
        self._warm_lock = asyncio.Lock()

    def _submit(self, coro, timeout: float):
        """Submit a coroutine to the persistent loop and block until done."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except TimeoutError:
            future.cancel()
            raise

    def _make_backend(self, thread_id: str, timeout: float):
        from .deepagents_backend import MayflowerSandboxBackend
        return MayflowerSandboxBackend(
            self._pool,
            thread_id=thread_id,
            allow_net=self._allow_net,
            stateful=True,
            timeout_seconds=timeout,
        )

    # ------------------------------------------------------------------
    # Public sync API
    # ------------------------------------------------------------------

    def execute(
        self,
        code: str,
        thread_id: str,
        timeout: float | None = None,
        is_shell: bool = False,
    ) -> tuple[str, int]:
        """Execute code in the sandbox. Thread-safe, uses protocol sentinels.

        Returns:
            (output, exit_code) where output is combined stdout+stderr.
        """
        t = timeout if timeout is not None else self._timeout_seconds
        sentinel = _SHELL_SENTINEL if is_shell else _PYTHON_SENTINEL
        command = f"{sentinel}\n{code}"
        try:
            res = self._submit(
                self._aexecute(command, thread_id, t),
                timeout=t + 10,
            )
            return res.output or "", res.exit_code
        except TimeoutError:
            return f"Timeout nach {t:.0f}s", -1
        except Exception as exc:
            return f"Sandbox-Fehler: {exc}", 1

    def list_files(
        self,
        thread_id: str,
        path: str = "/home",
    ) -> list["FileInfo"]:
        """List files in the sandbox VFS. Returns FileInfo list (empty on error)."""
        try:
            return self._submit(
                self._alist_files(thread_id, path),
                timeout=15,
            )
        except Exception as exc:
            logger.warning("list_files failed for %s: %s", thread_id, exc)
            return []

    def download_file(
        self,
        thread_id: str,
        path: str,
    ) -> bytes | None:
        """Download a file from the sandbox VFS. Returns None on error."""
        try:
            return self._submit(
                self._adownload_file(thread_id, path),
                timeout=30,
            )
        except Exception as exc:
            logger.warning("download_file failed for %s %s: %s", thread_id, path, exc)
            return None

    # ------------------------------------------------------------------
    # Async implementations (run inside the persistent loop)
    # ------------------------------------------------------------------

    async def _ensure_warmed(self, thread_id: str) -> None:
        """Install bundled Pyodide packages on first use of a thread.

        Packages are written into the thread's VFS so subsequent calls find
        them already installed without re-running micropip.
        """
        if not self._preinstall or thread_id in self._warmed_threads:
            return
        async with self._warm_lock:
            if thread_id in self._warmed_threads:
                return  # another coroutine beat us here
            pkgs = list(self._preinstall)
            install_code = (
                "__PYTHON__\n"
                "import micropip as _mp\n"
                f"await _mp.install({pkgs!r}, keep_going=True)\n"
                "del _mp"
            )
            logger.info("Pre-installing %s for thread %r …", pkgs, thread_id)
            backend = self._make_backend(thread_id, 120.0)
            try:
                await backend.aexecute(install_code)
                self._warmed_threads.add(thread_id)
                logger.info("Pre-install done for thread %r", thread_id)
            except Exception as exc:
                logger.warning("Pre-install failed for thread %r: %s", thread_id, exc)
                # Mark as warmed anyway so we don't retry on every call
                self._warmed_threads.add(thread_id)

    async def _aexecute(self, command: str, thread_id: str, timeout: float):
        await self._ensure_warmed(thread_id)
        backend = self._make_backend(thread_id, timeout)
        return await backend.aexecute(command)

    async def _alist_files(self, thread_id: str, path: str):
        backend = self._make_backend(thread_id, self._timeout_seconds)
        return await backend.als_info(path)

    async def _adownload_file(self, thread_id: str, path: str) -> bytes | None:
        backend = self._make_backend(thread_id, self._timeout_seconds)
        results = await backend.adownload_files([path])
        if results and results[0].content:
            return results[0].content
        return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Gracefully stop the background event loop."""
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)
        logger.info("SyncSandboxManager shut down")
