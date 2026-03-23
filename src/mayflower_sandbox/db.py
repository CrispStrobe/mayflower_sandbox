import asyncio
import re
import sqlite3
from typing import Any, AsyncIterator, Dict, List, Optional
from contextlib import asynccontextmanager

try:
    import asyncpg
except ImportError:
    class _DummyAsyncpg:
        class UndefinedTableError(Exception): pass
        class UndefinedColumnError(Exception): pass
        class CheckViolationError(Exception): pass
        class IntegrityConstraintViolationError(Exception): pass
    asyncpg = _DummyAsyncpg()  # type: ignore

def _translate_query(query: str) -> str:
    """Translate PostgreSQL query to SQLite syntax."""
    # Remove ::jsonb and ::text[] casts
    query = query.replace("::jsonb", "")
    query = query.replace("::text[]", "")
    
    # Handle information_schema.tables and pg_indexes
    if "information_schema.tables" in query.lower() or "pg_indexes" in query.lower() or "pg_database" in query.lower():
        # SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'x')
        query = re.sub(
            r"SELECT\s+1\s+FROM\s+information_schema\.tables\s+WHERE\s+(?:table_schema\s*=\s*'public'\s+AND\s+)?table_name\s*=\s*(['\"]\w+['\"])",
            r"SELECT 1 FROM sqlite_master WHERE type='table' AND name=\1",
            query,
            flags=re.IGNORECASE
        )
        # SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'sandbox_%'
        query = re.sub(
            r"SELECT\s+table_name\s+FROM\s+information_schema\.tables\s+WHERE\s+(?:table_schema\s*=\s*'public'\s+AND\s+)?table_name\s+LIKE\s+(['\"]%?\w+%?['\"])",
            r"SELECT name as table_name FROM sqlite_master WHERE type='table' AND name LIKE \1",
            query,
            flags=re.IGNORECASE
        )
        # SELECT indexname FROM pg_indexes WHERE tablename IN (...)
        query = re.sub(
            r"SELECT\s+indexname\s+FROM\s+pg_indexes\s+WHERE\s+tablename\s+IN\s+\((.*?)\)(?:\s+AND\s+schemaname\s*=\s*'public')?",
            r"SELECT CASE WHEN name LIKE 'sqlite_autoindex_%' THEN tbl_name || '_pkey' ELSE name END as indexname FROM sqlite_master WHERE type='index' AND tbl_name IN (\1)",
            query,
            flags=re.IGNORECASE
        )
        # SELECT 1 FROM pg_database WHERE datname = $1
        query = re.sub(
            r"SELECT\s+1\s+FROM\s+pg_database\s+WHERE\s+datname\s*=\s*(\$\d+|\?)",
            r"SELECT 1 WHERE 1=\1 OR 1=1", # Always return 1 for datname check in SQLite test
            query,
            flags=re.IGNORECASE
        )

    # Handle WHERE thread_id = ANY($1) or similar
    # Matches "= ANY($1)" or "= ANY(?)" with optional whitespace and optional $N
    query = re.sub(
        r"=\s*ANY\s*\(\s*(\$\d+|\?)\s*\)",
        r"IN (\1)",
        query,
        flags=re.IGNORECASE
    )
    
    # Handle NOW() - INTERVAL 'X days'
    # Match: NOW() - INTERVAL '(\d+) days?'
    query = re.sub(
        r"NOW\(\)\s*-\s*INTERVAL\s*'(\d+)\s+days?'",
        r"datetime('now', '-\1 day')",
        query,
        flags=re.IGNORECASE
    )
    
    # Handle NOW() + INTERVAL 'X days'
    query = re.sub(
        r"NOW\(\)\s*\+\s*INTERVAL\s*'(\d+)\s+days?'",
        r"datetime('now', '+\1 day')",
        query,
        flags=re.IGNORECASE
    )
    
    # Simple NOW() replacement
    query = query.replace("NOW()", "CURRENT_TIMESTAMP")
    
    # Handle DROP TABLE ... CASCADE
    query = re.sub(r"DROP\s+TABLE\s+(.*?)\s+CASCADE", r"DROP TABLE \1", query, flags=re.IGNORECASE)

    # Replace $1, $2 with ?
    # BUT wait: we need to do this AFTER any other positional logic
    # Actually, SQLite execute takes ? markers.
    # Our _execute_sync does replacements like IN ($1) -> IN (?,?,...).
    # If we replace $1 with ? here, we break that logic.
    # So let's MOVE the $N -> ? replacement to _execute_sync.
    return query

class SqliteConnection:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def _execute_sync(self, query: str, args: tuple) -> sqlite3.Cursor:
        query = _translate_query(query)
        
        # Handle list expansion for IN clauses if we replaced = ANY(?)
        # This is a bit of a hack but works for the known patterns in this codebase
        new_args = list(args)
        if " IN (" in query:
            # Sort by descending index to avoid shifting issues when replacing multiple?
            # Actually our current regex replace is simpler.
            for i, arg in enumerate(args):
                if isinstance(arg, list):
                    placeholders = ", ".join(["?"] * len(arg))
                    query = query.replace(f"IN (${i+1})", f"IN ({placeholders})")
                    query = query.replace(f"IN ($ {i+1})", f"IN ({placeholders})")
                    query = query.replace("IN (?)", f"IN ({placeholders})", 1)
                    
                    # Flatten the list into new_args at the correct position
                    # We need to find where this arg is in new_args.
                    # This is tricky because previous expansions change the indices.
                    # Let's just do it for the FIRST list arg found which is sufficient for our cleanup.
                    idx = new_args.index(arg)
                    new_args[idx:idx+1] = arg
                    break

        # Final replacement of all positional parameters to ? for SQLite
        query = re.sub(r'\$\d+', '?', query)
        query = re.sub(r'\$\s+\d+', '?', query)

        # Handle dicts/lists for JSON by letting sqlite3 raise an error if not text, 
        # but the codebase manually json.dumps metadata before insert.
        try:
            return self.conn.execute(query, tuple(new_args))
        except sqlite3.IntegrityError as e:
            msg = str(e).lower()
            if "check constraint failed" in msg:
                raise asyncpg.CheckViolationError(str(e)) from e
            raise asyncpg.IntegrityConstraintViolationError(str(e)) from e

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        def run():
            cursor = self._execute_sync(query, args)
            return [dict(row) for row in cursor.fetchall()]
        return await asyncio.to_thread(run)

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        def run():
            cursor = self._execute_sync(query, args)
            row = cursor.fetchone()
            return dict(row) if row else None
        return await asyncio.to_thread(run)

    async def fetchval(self, query: str, *args: Any) -> Any:
        def run():
            cursor = self._execute_sync(query, args)
            row = cursor.fetchone()
            if not row:
                return None
            val = row[0]
            # Heuristic: if we are expecting a boolean (like in file_exists) 
            # and we got 0/1, keep it as is because 0 == False.
            # But the test uses 'is False'.
            # If the query is "SELECT EXISTS..." or "SELECT count..." 
            # we might want to cast.
            if query.strip().lower().startswith("select exists"):
                return bool(val)
            return val
        return await asyncio.to_thread(run)

    async def execute(self, query: str, *args: Any) -> str:
        def run():
            if not args and ";" in query:
                # Potential multi-statement script (common in migrations)
                # sqlite3.execute() only supports one statement at a time.
                # executescript() supports multiple but no parameters.
                # We translate first.
                translated = _translate_query(query)
                self.conn.executescript(translated)
                self.conn.commit()
                return "DONE"
            
            cursor = self._execute_sync(query, args)
            self.conn.commit()
            return f"DONE {cursor.rowcount}"
        return await asyncio.to_thread(run)

class SqliteDatabase:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        # Enable foreign keys and WAL mode for better concurrency
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with schema."""
        schema = """
        CREATE TABLE IF NOT EXISTS sandbox_sessions (
            thread_id TEXT PRIMARY KEY,
            last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS sandbox_filesystem (
            thread_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content BLOB NOT NULL,
            content_type TEXT NOT NULL,
            size INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT DEFAULT '{}',
            PRIMARY KEY (thread_id, file_path),
            CONSTRAINT fk_thread FOREIGN KEY (thread_id)
                REFERENCES sandbox_sessions(thread_id)
                ON DELETE CASCADE,
            CONSTRAINT chk_size CHECK (size <= 20971520)
        );

        CREATE TABLE IF NOT EXISTS sandbox_session_bytes (
            thread_id TEXT PRIMARY KEY,
            session_bytes BLOB,
            session_metadata TEXT DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_session FOREIGN KEY (thread_id)
                REFERENCES sandbox_sessions(thread_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sandbox_skills (
            thread_id TEXT NOT NULL,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (thread_id, name)
        );

        CREATE TABLE IF NOT EXISTS sandbox_mcp_servers (
            thread_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            headers TEXT,
            auth TEXT,
            schemas TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (thread_id, name)
        );
        """
        self._conn.executescript(schema)
        self._conn.commit()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[SqliteConnection]:
        yield SqliteConnection(self._conn)

    async def close(self):
        self._conn.close()

async def create_sqlite_pool(db_path: str) -> SqliteDatabase:
    """Create a SQLite database pool that mimics asyncpg.Pool."""
    return SqliteDatabase(db_path)
