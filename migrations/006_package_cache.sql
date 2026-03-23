-- Persistent Library Caching Support
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
