# Mayflower Sandbox

Production-ready Python sandbox implementing the [DeepAgents](https://github.com/mayflower/deepagents) `SandboxBackendProtocol`, with PostgreSQL-backed virtual filesystem and document processing helpers.

Execute untrusted Python code via Pyodide WebAssembly, run shell commands via BusyBox WASM, process documents (Word, Excel, PowerPoint, PDF), and maintain persistent state across sessions -- all with complete thread isolation.

## Getting Started

- [Installation](getting-started/installation.md) -- Prerequisites, package install, database setup
- [Quick Start](getting-started/quickstart.md) -- Create a backend, execute code, work with files

## How-To Guides

- [Document Processing](how-to/document-processing.md) -- Use and create document helpers (Word, Excel, PowerPoint, PDF)
- [Skills & MCP](how-to/skills-and-mcp.md) -- Install Claude Skills and bind MCP servers
- [VFS Snapshots](how-to/vfs-snapshots.md) -- Create state clones for experimentation and rollback
- [Network Control](how-to/network-control.md) -- Fine-grained domain allowlisting for egress security
- [Collaborative Workspaces](how-to/collaborative-workspaces.md) -- Shared VFS storage for multi-agent collaboration
- [TypeScript Bridge](how-to/typescript-bridge.md) -- Execute TypeScript from within your Python sandbox
- [Package Caching](how-to/package-caching.md) -- Faster library installs via database wheel cache
- [Debugging](how-to/debugging.md) -- Attach Chrome DevTools/VS Code to the sandbox
- [Deployment](how-to/deployment.md) -- Docker, testing, quality checks, production configuration
- [Troubleshooting](how-to/troubleshooting.md) -- Common issues and solutions

## Reference

- [Backend API](reference/backend-api.md) -- `MayflowerSandboxBackend` and `PostgresBackend` method signatures
- [Configuration](reference/configuration.md) -- Environment variables, database schema, tuning
- [Document Helpers](reference/document-helpers.md) -- API tables for all document helper functions
- [Internal API](reference/api.md) -- SandboxExecutor, VirtualFilesystem, SandboxManager, FileServer, CleanupJob

## Architecture

- [System Design](architecture/system-design.md) -- Component overview and data flow
- [Command Routing](architecture/command-routing.md) -- How `execute()` dispatches to Pyodide or BusyBox
- [Security Model](architecture/security-model.md) -- WASM sandboxing, thread isolation, path validation
- [Performance](architecture/performance.md) -- Worker pool benchmarks, stateful execution, tuning
