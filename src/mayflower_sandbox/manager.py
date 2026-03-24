"""Session lifecycle management for sandbox threads."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any



logger = logging.getLogger(__name__)


class SessionNotFoundError(Exception):
    """Session does not exist."""


class SessionExpiredError(Exception):
    """Session has expired."""


class SandboxManager:
    """Manages lifecycle of sandbox sessions.

    Responsibilities:
    - Session creation and retrieval
    - Metadata management
    - Expiration tracking
    - Cleanup of expired sessions
    """

    def __init__(
        self,
        db_pool: Any,
        default_expiration_days: int = 180,
    ):
        """Initialize manager.

        Args:
            db_pool: PostgreSQL connection pool
            default_expiration_days: Default TTL for new sessions
        """
        self.db = db_pool
        self.default_expiration_days = default_expiration_days

    def _safe_dict(self, s: Any) -> dict:
        """Convert a database record to a dict, but handle Mocks safely."""
        if s is None:
            return {}
        if hasattr(s, "items") and not hasattr(s, "mock_calls"):
            return dict(s)
        return s

    async def create_session(
        self,
        thread_id: str,
        metadata: dict | None = None,
        vfs_id: str | None = None,
    ) -> dict:
        """Create a new session explicitly.

        Args:
            thread_id: Thread identifier
            metadata: Optional metadata
            vfs_id: Optional shared VFS identifier. Defaults to thread_id.

        Returns:
            Session record
        """
        expires_at = datetime.now() + timedelta(days=self.default_expiration_days)
        effective_vfs_id = vfs_id or thread_id
        
        async with self.db.acquire() as conn:
            session = await conn.fetchrow(
                """
                INSERT INTO sandbox_sessions (
                    thread_id, expires_at, metadata, vfs_id
                ) VALUES ($1, $2, $3::jsonb, $4)
                RETURNING *
            """,
                thread_id,
                expires_at,
                json.dumps(metadata or {}),
                effective_vfs_id,
            )

            logger.info(f"Created session {thread_id} (VFS: {effective_vfs_id})")
            return self._safe_dict(session)

    async def get_or_create_session(
        self,
        thread_id: str,
        metadata: dict | None = None,
        vfs_id: str | None = None,
    ) -> dict:
        """Get existing session or create new one.

        Args:
            thread_id: Thread identifier
            metadata: Optional metadata for new session
            vfs_id: Optional shared VFS identifier. Defaults to thread_id.

        Returns:
            Session record with all fields

        Raises:
            SessionExpiredError: If session exists but has expired
        """
        async with self.db.acquire() as conn:
            # Try to get existing session
            session = await conn.fetchrow(
                "SELECT * FROM sandbox_sessions WHERE thread_id = $1", thread_id
            )

            if session:
                # Check if expired
                expires_at = session["expires_at"]
                if isinstance(expires_at, datetime):
                    if expires_at < datetime.now():
                        raise SessionExpiredError(
                            f"Session {thread_id} expired at {expires_at}"
                        )

                # Update last accessed
                await self.update_last_accessed(thread_id)
                return self._safe_dict(session)

            # Create new session
            effective_vfs_id = vfs_id or thread_id
            expires_at = datetime.now() + timedelta(days=self.default_expiration_days)
            session = await conn.fetchrow(
                """
                INSERT INTO sandbox_sessions (
                    thread_id, expires_at, metadata, vfs_id
                ) VALUES ($1, $2, $3::jsonb, $4)
                RETURNING *
            """,
                thread_id,
                expires_at,
                json.dumps(metadata or {}),
                effective_vfs_id,
            )

            logger.info(f"Created new session for thread {thread_id} (VFS: {effective_vfs_id}), expires {expires_at}")
            return self._safe_dict(session)

    async def get_session(self, thread_id: str) -> dict:
        """Get existing session.

        Args:
            thread_id: Thread identifier

        Returns:
            Session record

        Raises:
            SessionNotFoundError: If session does not exist
            SessionExpiredError: If session has expired
        """
        async with self.db.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT * FROM sandbox_sessions WHERE thread_id = $1", thread_id
            )

            if not session:
                raise SessionNotFoundError(f"Session {thread_id} not found")

            # Check if expired
            expires_at = session["expires_at"]
            if isinstance(expires_at, datetime):
                if expires_at < datetime.now():
                    raise SessionExpiredError(
                        f"Session {thread_id} expired at {expires_at}"
                    )

            return self._safe_dict(session)

    async def update_last_accessed(self, thread_id: str) -> None:
        """Update last accessed timestamp.

        Args:
            thread_id: Thread identifier
        """
        async with self.db.acquire() as conn:
            await conn.execute(
                "UPDATE sandbox_sessions SET last_accessed = NOW() WHERE thread_id = $1",
                thread_id,
            )

    async def cleanup_expired_sessions(self) -> int:
        """Delete all expired sessions.

        Returns:
            Number of sessions deleted
        """
        async with self.db.acquire() as conn:
            # Get IDs of expired sessions first for logging
            expired = await conn.fetch(
                "SELECT thread_id FROM sandbox_sessions WHERE expires_at < NOW()"
            )
            thread_ids = [r["thread_id"] for r in expired]

            if not thread_ids:
                return 0

            # Delete sessions (cascades to filesystem and session_bytes)
            result = await conn.execute(
                "DELETE FROM sandbox_sessions WHERE thread_id = ANY($1)",
                thread_ids,
            )

            # Parse "DELETE N" result
            count = int(result.split()[-1])
            logger.info(f"Cleaned up {count} expired sessions: {thread_ids}")
            return count

    async def session_exists(self, thread_id: str) -> bool:
        """Check if session exists.

        Args:
            thread_id: Thread identifier

        Returns:
            True if exists, False otherwise
        """
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM sandbox_sessions WHERE thread_id = $1", thread_id
            )
            return row is not None

    async def list_active_sessions(self, limit: int = 100) -> list[dict]:
        """List active (non-expired) sessions.

        Args:
            limit: Maximum number of sessions to return

        Returns:
            List of session records
        """
        async with self.db.acquire() as conn:
            sessions = await conn.fetch(
                """
                SELECT * FROM sandbox_sessions
                WHERE expires_at > NOW()
                ORDER BY last_accessed DESC
                LIMIT $1
            """,
                limit,
            )

            return [self._safe_dict(s) for s in sessions]

    async def create_snapshot(self, thread_id: str, ttl_days: int = 1) -> str:
        """Create a point-in-time snapshot of a session.

        Args:
            thread_id: Original thread to snapshot
            ttl_days: How long the snapshot should live before auto-cleanup

        Returns:
            New snapshot thread_id
        """
        import uuid
        snapshot_id = f"{thread_id}@snap_{uuid.uuid4().hex[:8]}"
        expires_at = datetime.now() + timedelta(days=ttl_days)
        
        async with self.db.acquire() as conn:
            # Check if parent exists
            parent = await conn.fetchrow("SELECT * FROM sandbox_sessions WHERE thread_id = $1", thread_id)
            if not parent:
                raise SessionNotFoundError(f"Session {thread_id} not found")
                
            # 1. Create snapshot session
            metadata = parent["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            
            parent_vfs_id = parent.get("vfs_id") or thread_id
            
            # Note: PostgreSQL requires columns to exist. If the migration hasn't run, 
            # this will fail. We should handle it gracefully or rely on the user running migrations.
            try:
                await conn.execute(
                    """
                    INSERT INTO sandbox_sessions (
                        thread_id, expires_at, metadata, parent_thread_id, vfs_id
                    ) VALUES ($1, $2, $3::jsonb, $4, $5)
                    """,
                    snapshot_id,
                    expires_at,
                    json.dumps(metadata),
                    thread_id,
                    snapshot_id # Snapshots are ALWAYS isolated clones
                )
            except Exception as e:
                # If parent_thread_id doesn't exist yet (migration not run)
                if "parent_thread_id" in str(e).lower() or "no column" in str(e).lower():
                    raise RuntimeError("Database migration for VFS snapshots has not been applied. Please run migrations/004_vfs_snapshots.sql") from e
                raise
            
            # 2. Copy filesystem (from parent VFS)
            res = await conn.execute(
                """
                INSERT INTO sandbox_filesystem (
                    thread_id, vfs_id, file_path, content, content_type, size, created_at, modified_at, metadata
                )
                SELECT $1, $1, file_path, content, content_type, size, created_at, modified_at, metadata
                FROM sandbox_filesystem
                WHERE vfs_id = $2
                """,
                snapshot_id, parent_vfs_id
            )
            logger.debug(f"Snapshot {snapshot_id}: copied files from {parent_vfs_id}, result: {res}")
            
            # 3. Copy session bytes
            await conn.execute(
                """
                INSERT INTO sandbox_session_bytes (
                    thread_id, session_bytes, session_metadata, updated_at
                )
                SELECT $1, session_bytes, session_metadata, updated_at
                FROM sandbox_session_bytes
                WHERE thread_id = $2
                """,
                snapshot_id, thread_id
            )
            
        logger.info(f"Created snapshot {snapshot_id} from {thread_id}")
        return snapshot_id

    async def restore_snapshot(self, snapshot_id: str, target_thread_id: str | None = None) -> str:
        """Restore a snapshot to a target session (or its parent).
        
        Args:
            snapshot_id: The snapshot thread_id
            target_thread_id: The thread to overwrite. If None, overwrites the parent.
        """
        async with self.db.acquire() as conn:
            snap = await conn.fetchrow("SELECT * FROM sandbox_sessions WHERE thread_id = $1", snapshot_id)
            if not snap:
                raise SessionNotFoundError(f"Snapshot {snapshot_id} not found")
                
            # If the database doesn't have parent_thread_id, snap won't either.
            target = target_thread_id or snap.get("parent_thread_id")
            if not target:
                raise ValueError("No target thread_id provided and snapshot has no parent.")
                
            # Make sure target exists
            target_session = await conn.fetchrow("SELECT * FROM sandbox_sessions WHERE thread_id = $1", target)
            
            if not target_session:
                target_vfs_id = target
                metadata = snap["metadata"]
                if isinstance(metadata, str):
                    metadata = json.loads(metadata)
                expires_at = datetime.now() + timedelta(days=self.default_expiration_days)
                await conn.execute(
                    """
                    INSERT INTO sandbox_sessions (thread_id, expires_at, metadata, vfs_id)
                    VALUES ($1, $2, $3::jsonb, $4)
                    """, target, expires_at, json.dumps(metadata), target_vfs_id
                )
            else:
                # Use existing vfs_id if it exists and is different (collaborative), 
                # otherwise use thread_id (isolated)
                target_vfs_id = target_session.get("vfs_id") or target
                if target_vfs_id != target:
                    # In collaborative mode, we want to restore specifically to THAT vfs_id
                    pass
                else:
                    # In isolated mode, ensure we use the thread_id
                    target_vfs_id = target
                
            snapshot_vfs_id = snap.get("vfs_id") or snapshot_id
            logger.debug(f"Restoring snapshot {snapshot_id} (VFS: {snapshot_vfs_id}) to target {target} (VFS: {target_vfs_id})")
                
            # Delete existing target files and bytes
            await conn.execute("DELETE FROM sandbox_filesystem WHERE vfs_id = $1", target_vfs_id)
            await conn.execute("DELETE FROM sandbox_session_bytes WHERE thread_id = $1", target)
            
            # Copy from snapshot to target
            # Note: We set thread_id to target so this thread 'owns' these restored files 
            # for cleanup purposes, but they live in target_vfs_id so all collaborators see them.
            await conn.execute(
                """
                INSERT INTO sandbox_filesystem (
                    thread_id, vfs_id, file_path, content, content_type, size, created_at, modified_at, metadata
                )
                SELECT $1, $2, file_path, content, content_type, size, created_at, modified_at, metadata
                FROM sandbox_filesystem
                WHERE vfs_id = $3
                """,
                target, target_vfs_id, snapshot_vfs_id
            )
            
            await conn.execute(
                """
                INSERT INTO sandbox_session_bytes (
                    thread_id, session_bytes, session_metadata, updated_at
                )
                SELECT $1, session_bytes, session_metadata, updated_at
                FROM sandbox_session_bytes
                WHERE thread_id = $2
                """,
                target, snapshot_id
            )
            
        logger.info(f"Restored snapshot {snapshot_id} to {target}")
        return target
