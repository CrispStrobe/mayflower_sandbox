"""PostgreSQL-backed virtual filesystem for sandbox.

This VFS serves as the persistent layer. Files stored here will be:
- Loaded into Pyodide memfs before execution (pre-load)
- Saved from Pyodide memfs after execution (post-sync)
"""

import logging
import mimetypes
import re
from pathlib import Path
from typing import Any



logger = logging.getLogger(__name__)


class FileNotFoundError(Exception):
    """File does not exist."""


class FileTooLargeError(Exception):
    """File exceeds size limit."""


class InvalidPathError(Exception):
    """Invalid path or security violation."""


class VirtualFilesystem:
    """Virtual filesystem implementation.

    Responsibilities:
    - Persistent file storage in PostgreSQL or SQLite
    - Path validation and sanitization
    """

    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

    def __init__(self, db_pool: Any, thread_id: str, vfs_id: str | None = None):
        """Initialize filesystem for specific thread.

        Args:
            db_pool: PostgreSQL connection pool
            thread_id: Thread identifier for isolation
            vfs_id: Optional shared VFS identifier. Defaults to thread_id.
        """
        self.db = db_pool
        self.thread_id = thread_id
        self.vfs_id = vfs_id or thread_id

    def _safe_dict(self, s: Any) -> dict:
        """Convert a database record to a dict, but handle Mocks safely."""
        if s is None:
            return {}
        if hasattr(s, "items") and "Mock" not in str(type(s)):
            return dict(s)
        return s

    async def ensure_session(self) -> None:
        """Ensure session exists in database for this thread_id.

        Creates session if it doesn't exist. This is called automatically
        before write operations.
        Sets a default expiration of 1 day from now if creating a new session.
        """
        async with self.db.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sandbox_sessions (thread_id, expires_at, metadata, vfs_id)
                VALUES ($1, NOW() + INTERVAL '1 day', '{}', $2)
                ON CONFLICT (thread_id) DO NOTHING
                """,
                self.thread_id,
                self.vfs_id,
            )

    def validate_path(self, file_path: str) -> str:
        """Validate and normalize file path.

        Args:
            file_path: Path to validate

        Returns:
            Normalized absolute path

        Raises:
            InvalidPathError: If path is invalid or malicious
        """
        if not file_path:
            raise InvalidPathError("Path cannot be empty")

        # Basic path traversal protection
        if ".." in file_path:
            raise InvalidPathError("Path traversal not allowed")

        # Normalize to absolute path
        path = Path(file_path)
        if not path.is_absolute():
            path = Path("/") / path

        return str(path)

    def detect_content_type(self, file_path: str, content: bytes) -> str:
        """Detect MIME type based on path and content.

        Args:
            file_path: File path for extension detection
            content: File content for magic detection

        Returns:
            MIME type string
        """
        # Try extension-based detection first
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            return mime_type

        # Basic magic number detection
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"%PDF-"):
            return "application/pdf"
        if content.startswith(b"PK\x03\x04"):
            # Excel/Word/PPT are all ZIP based, but extension detection
            # should have caught them above. Fallback to generic binary.
            return "application/octet-stream"

        # Default to text or binary based on null-byte presence
        return "text/plain" if b"\x00" not in content else "application/octet-stream"

    async def write_file(
        self,
        file_path: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict:
        """Write file to virtual filesystem.

        Args:
            file_path: Absolute path to the file
            content: Binary file content
            content_type: Optional MIME type (autodetected if None)

        Returns:
            Dictionary with file metadata

        Raises:
            FileTooLargeError: If file exceeds size limit
            InvalidPathError: If path is invalid
        """
        normalized_path = self.validate_path(file_path)
        size = len(content)

        if size > self.MAX_FILE_SIZE:
            raise FileTooLargeError(
                f"File {file_path} exceeds {self.MAX_FILE_SIZE / 1024 / 1024}MB limit"
            )

        if content_type is None:
            content_type = self.detect_content_type(normalized_path, content)

        # Lazily ensure session exists before writing
        await self.ensure_session()

        # Upsert file
        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                INSERT INTO sandbox_filesystem (
                    thread_id, vfs_id, file_path, content, content_type, size
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (vfs_id, file_path)
                DO UPDATE SET
                    content = EXCLUDED.content,
                    content_type = EXCLUDED.content_type,
                    size = EXCLUDED.size,
                    modified_at = NOW()
                RETURNING *
            """,
                self.thread_id,
                self.vfs_id,
                normalized_path,
                content,
                content_type,
                size,
            )

            logger.debug(f"Wrote file {normalized_path} ({size} bytes) for vfs {self.vfs_id}")

            return self._safe_dict(result)

    async def read_file(self, file_path: str) -> dict:
        """Read file from filesystem.

        Args:
            file_path: Path to read

        Returns:
            Dict with content, content_type, size, etc.

        Raises:
            InvalidPathError: If path is invalid
            FileNotFoundError: If file doesn't exist
        """
        normalized_path = self.validate_path(file_path)

        async with self.db.acquire() as conn:
            result = await conn.fetchrow(
                """
                SELECT * FROM sandbox_filesystem
                WHERE vfs_id = $1 AND file_path = $2
            """,
                self.vfs_id,
                normalized_path,
            )

            if not result:
                raise FileNotFoundError(
                    f"File {normalized_path} not found in thread {self.thread_id}"
                )

            return self._safe_dict(result)

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from filesystem.

        Args:
            file_path: Path to delete

        Returns:
            True if file was deleted, False if didn't exist

        Raises:
            InvalidPathError: If path is invalid
        """
        normalized_path = self.validate_path(file_path)

        async with self.db.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM sandbox_filesystem
                WHERE vfs_id = $1 AND file_path = $2
            """,
                self.vfs_id,
                normalized_path,
            )

            # Parse "DELETE N" result
            deleted = int(result.split()[-1])
            return deleted > 0

    async def list_files(self, pattern: str | None = None) -> list[dict]:
        """List all files in filesystem.

        Args:
            pattern: Optional SQL LIKE pattern for filtering

        Returns:
            List of file metadata dicts
        """
        async with self.db.acquire() as conn:
            if pattern:
                files = await conn.fetch(
                    """
                    SELECT * FROM sandbox_filesystem
                    WHERE vfs_id = $1 AND file_path LIKE $2
                    ORDER BY file_path
                """,
                    self.vfs_id,
                    pattern,
                )
            else:
                files = await conn.fetch(
                    """
                    SELECT * FROM sandbox_filesystem
                    WHERE vfs_id = $1
                    ORDER BY file_path
                """,
                    self.vfs_id,
                )

            return [self._safe_dict(f) for f in files]

    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists.

        Args:
            file_path: Path to check

        Returns:
            True if file exists
        """
        try:
            normalized_path = self.validate_path(file_path)
            async with self.db.acquire() as conn:
                result = await conn.fetchval(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM sandbox_filesystem
                        WHERE vfs_id = $1 AND file_path = $2
                    )
                """,
                    self.vfs_id,
                    normalized_path,
                )
                return bool(result)
        except InvalidPathError:
            return False

    async def get_all_files_for_pyodide(self) -> dict[str, bytes]:
        """Get all files as dict for Pyodide pre-load.

        Returns:
            Dict mapping file_path → content (bytes)
        """
        files = await self.list_files()
        return {f["file_path"]: f["content"] for f in files}
