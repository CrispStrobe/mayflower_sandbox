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
    query = query.replace("BYTEA", "BLOB")
    query = query.replace("JSONB", "TEXT")
    # Handle NOW() - INTERVAL 'X days' or CURRENT_TIMESTAMP - INTERVAL 'X days'
    query = re.sub(
        r"(?:NOW\(\)|CURRENT_TIMESTAMP)\s*-\s*INTERVAL\s*'(\d+)\s+days?'",
        r"datetime('now', '-\1 day')",
        query,
        flags=re.IGNORECASE
    )
    
    # Handle NOW() + INTERVAL 'X days' or CURRENT_TIMESTAMP + INTERVAL 'X days'
    query = re.sub(
        r"(?:NOW\(\)|CURRENT_TIMESTAMP)\s*\+\s*INTERVAL\s*'(\d+)\s+days?'",
        r"datetime('now', '+\1 day')",
        query,
        flags=re.IGNORECASE
    )
    
    query = query.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    query = query.replace("NOW()", "CURRENT_TIMESTAMP")
    
    # Simple NOW() replacement
    query = query.replace("NOW()", "CURRENT_TIMESTAMP")
    
    # Handle information_schema.tables and pg_indexes
    if "information_schema.tables" in query.lower() or "pg_indexes" in query.lower() or "pg_database" in query.lower():
        # SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'x')
        # matches the one in db_pool fixture
        query = re.sub(
            r"SELECT\s+EXISTS\s*\(\s*SELECT\s+1\s+FROM\s+information_schema\.tables\s+WHERE\s+(?:table_schema\s*=\s*'public'\s+AND\s+)?table_name\s*=\s*(['\"]\w+['\"])\s*\)",
            r"SELECT EXISTS (SELECT 1 FROM sqlite_master WHERE type='table' AND name=\1)",
            query,
            flags=re.IGNORECASE
        )
        # SELECT 1 FROM information_schema.tables WHERE table_name = 'x'
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
    
    # Replace $1, $2 with ?1, ?2 for SQLite (allows reuse)
    query = re.sub(r'\$(\d+)', r'?\1', query)
    query = re.sub(r'\$\s+(\d+)', r'?\1', query)

    # Handle DROP TABLE ... CASCADE
    query = re.sub(r"DROP\s+TABLE\s+(.*?)\s+CASCADE", r"DROP TABLE \1", query, flags=re.IGNORECASE)

    return query

class SqliteConnection:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    def _inject_legacy_columns(self, query: str, args: tuple) -> tuple[str, tuple]:
        """Inject vfs_id into legacy INSERT statements. 
        Note: We only modify the SQL string here. SQLite's indexed ?N bindings 
        will handle the argument reuse if we use $1, $1 -> ?1, ?1.
        """
        q_lower = query.lower()
        if "vfs_id" in q_lower or "insert into" not in q_lower:
            return query, args

        is_sessions = "sandbox_sessions" in q_lower
        is_fs = "sandbox_filesystem" in q_lower
        
        if not (is_sessions or is_fs):
            return query, args

        # 1. Inject 'vfs_id' into column list
        col_list_match = re.search(r"(\(\s*thread_id\s*,)", query, flags=re.IGNORECASE | re.DOTALL)
        if not col_list_match:
            return query, args
            
        new_query = query[:col_list_match.start()] + "(thread_id, vfs_id," + query[col_list_match.end():]
        
        # 2. Inject value into VALUES clause
        parts = re.split(r"VALUES", new_query, flags=re.IGNORECASE)
        if len(parts) != 2:
            return query, args
            
        prefix = parts[0]
        values_and_rest = parts[1]
        
        on_conflict_parts = re.split(r"ON CONFLICT", values_and_rest, flags=re.IGNORECASE)
        rows_part = on_conflict_parts[0]
        suffix = " ON CONFLICT" + on_conflict_parts[1] if len(on_conflict_parts) > 1 else ""
        
        def duplicate_first_value(m):
            row_content = m.group(1)
            comma_idx = row_content.find(",")
            if comma_idx == -1:
                return f"({row_content}, {row_content})"
            first_val = row_content[:comma_idx].strip()
            return f"({first_val}, {row_content})"

        new_rows_part = re.sub(r"\(\s*([^)]+)\s*\)", duplicate_first_value, rows_part)
        new_query = f"{prefix}VALUES{new_rows_part}{suffix}"
        
        return new_query, args

    def _execute_sync(self, query: str, args: tuple) -> sqlite3.Cursor:
        # Before translation, handle legacy column injection
        query, args = self._inject_legacy_columns(query, args)
        
        # We translate FIRST now to have a consistent ?N style
        query = _translate_query(query)

        # Handle list expansion for IN (?) clauses
        new_args = list(args)
        if " IN (" in query.upper():
            for i, arg in enumerate(args):
                if isinstance(arg, list):
                    placeholders = ", ".join(["?"] * len(arg))
                    # Handle indexed ?N style (from _translate_query)
                    target = f"?{i+1}"
                    target_escaped = re.escape(target)
                    query = re.sub(rf"IN\s*\(\s*{target_escaped}\s*\)", f"IN ({placeholders})", query, flags=re.IGNORECASE)
                    # Handle generic ?
                    query = query.replace("IN (?)", f"IN ({placeholders})", 1)
                    
                    # Flatten the list into new_args at the correct position
                    new_args[i:i+1] = arg
                    break

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
                query_injected, _ = self._inject_legacy_columns(query, ())
                translated = _translate_query(query_injected)
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            parent_thread_id TEXT REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE,
            vfs_id TEXT
        );

        CREATE TABLE IF NOT EXISTS sandbox_filesystem (
            thread_id TEXT NOT NULL,
            vfs_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            content BLOB NOT NULL,
            content_type TEXT NOT NULL,
            size INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT DEFAULT '{}',
            PRIMARY KEY (vfs_id, file_path),
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
            vfs_id TEXT,
            PRIMARY KEY (thread_id, name)
        );

        CREATE TABLE IF NOT EXISTS sandbox_package_cache (
            package_name TEXT NOT NULL,
            version TEXT NOT NULL,
            pyodide_version TEXT NOT NULL,
            filename TEXT NOT NULL,
            content BLOB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (package_name, version, pyodide_version)
        );

        CREATE INDEX IF NOT EXISTS idx_sandbox_package_cache_lookup ON sandbox_package_cache(package_name, version);

        -- Triggers to ensure vfs_id is never NULL for new collaborative features
        CREATE TRIGGER IF NOT EXISTS trg_sandbox_sessions_vfs_id
        AFTER INSERT ON sandbox_sessions
        FOR EACH ROW
        WHEN NEW.vfs_id IS NULL
        BEGIN
            UPDATE sandbox_sessions SET vfs_id = NEW.thread_id WHERE thread_id = NEW.thread_id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_sandbox_filesystem_vfs_id
        AFTER INSERT ON sandbox_filesystem
        FOR EACH ROW
        WHEN NEW.vfs_id IS NULL
        BEGIN
            UPDATE sandbox_filesystem SET vfs_id = NEW.thread_id 
            WHERE thread_id = NEW.thread_id AND file_path = NEW.file_path;
        END;
        """
        self._conn.executescript(schema)
        self._conn.commit()

        # Handle migrations for existing DBs
        try:
            self._conn.execute("ALTER TABLE sandbox_sessions ADD COLUMN parent_thread_id TEXT REFERENCES sandbox_sessions(thread_id) ON DELETE CASCADE")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass # Column already exists

        try:
            self._conn.execute("ALTER TABLE sandbox_sessions ADD COLUMN vfs_id TEXT")
            self._conn.execute("UPDATE sandbox_sessions SET vfs_id = thread_id WHERE vfs_id IS NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        try:
            self._conn.execute("ALTER TABLE sandbox_filesystem ADD COLUMN vfs_id TEXT")
            self._conn.execute("UPDATE sandbox_filesystem SET vfs_id = thread_id WHERE vfs_id IS NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

        try:
            self._conn.execute("ALTER TABLE sandbox_mcp_servers ADD COLUMN vfs_id TEXT")
            self._conn.execute("UPDATE sandbox_mcp_servers SET vfs_id = thread_id WHERE vfs_id IS NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[SqliteConnection]:
        yield SqliteConnection(self._conn)

    async def close(self):
        self._conn.close()

async def create_sqlite_pool(db_path: str) -> SqliteDatabase:
    """Create a SQLite database pool that mimics asyncpg.Pool."""
    return SqliteDatabase(db_path)
