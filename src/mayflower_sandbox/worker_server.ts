/**
 * Mayflower Sandbox - Long-Running Pyodide Worker
 *
 * JSON-RPC server that keeps Pyodide loaded in memory for fast execution.
 * Designed to be used in a process pool for 70-95% performance improvement.
 */

import { loadPyodide } from "npm:pyodide@0.28.3";
import { snapshotFiles, collectFilesFromPaths } from "./fs_utils.ts";
import {
  errorToString,
  filterMicropipMessages,
  createStdoutHandler,
  createSuppressedStdout,
  createFileTracker,
  findChangedFiles,
} from "./worker_utils.ts";

// Re-export for backwards compatibility
export {
  errorToString,
  filterMicropipMessages,
  createStdoutHandler,
  createSuppressedStdout,
  createFileTracker,
  findChangedFiles,
} from "./worker_utils.ts";

const START_TIME = Date.now();

interface ExecuteRequest {
  code: string;
  thread_id: string;
  stateful?: boolean;
  session_bytes?: number[];
  session_metadata?: Record<string, unknown>;
  files?: Record<string, number[]>;
  timeout_ms?: number;
}

interface ExecuteResult {
  success: boolean;
  stdout: string;
  stderr: string;
  result: unknown;
  session_bytes?: number[];
  session_metadata?: Record<string, unknown>;
  created_files?: Array<{ path: string; content: number[] }>;
  files?: Record<string, number[]>;
  execution_time_ms: number;
}

interface JsonRpcRequest {
  jsonrpc: "2.0";
  id: number | string;
  method: string;
  params: any;
}

interface JsonRpcResponse {
  jsonrpc: "2.0";
  id: number | string;
  result?: any;
  error?: {
    code: number;
    message: string;
  };
}

// File operations (snapshotFiles, collectFiles, collectFilesFromPaths)
// are now imported from fs_utils.ts to reduce duplication
// Utility functions (errorToString, filterMicropipMessages, etc.)
// are now imported from worker_utils.ts

/**
 * Restore session state from bytes
 */
async function restoreSession(
  pyodide: any,
  sessionBytes: number[],
): Promise<void> {
  await pyodide.runPythonAsync(`
try:
    import cloudpickle
except ImportError:
    import micropip
    await micropip.install('cloudpickle')
    import cloudpickle
`);

  await pyodide.runPythonAsync(`
_session_bytes = bytes(${JSON.stringify(Array.from(sessionBytes))})
_session_obj = cloudpickle.loads(_session_bytes)
# Clear all user-defined names before applying session to prevent state
# from a previous thread's execution leaking into this session.
_skip = frozenset({'_session_bytes', '_session_obj', '_skip', 'cloudpickle', 'micropip'})
for _k in [k for k in list(globals()) if not k.startswith('__') and k not in _skip]:
    del globals()[_k]
globals().pop('_k', None)
globals().update(_session_obj)
del _session_bytes, _session_obj, _skip
`);
}

/**
 * Save session state to bytes
 */
async function saveSession(pyodide: any): Promise<number[]> {
  const sessionBytesResult = await pyodide.runPythonAsync(`
import types
_globals_snapshot = dict(globals())
_session_dict = {}
for k, v in _globals_snapshot.items():
    if k.startswith('_'):
        continue
    if isinstance(v, type) and v.__module__ == 'builtins':
        continue
    if hasattr(v, 'read') or hasattr(v, 'write'):
        continue
    # Filter out JsProxy objects which break cloudpickle
    if v.__class__.__name__ == 'JsProxy':
        continue
    _session_dict[k] = v
list(cloudpickle.dumps(_session_dict))
`);
  return sessionBytesResult.toJs();
}

/**
 * Mount files to Pyodide filesystem
 */
function mountFiles(pyodide: any, files: Record<string, number[]>): void {
  for (const [path, content] of Object.entries(files)) {
    const dir = path.substring(0, path.lastIndexOf("/"));
    if (dir && dir !== "/") {
      pyodide.FS.mkdirTree(dir);
    }
    pyodide.FS.writeFile(path, new Uint8Array(content));
  }
}


/**
 * Execution context for managing stdout/stderr buffers
 */
interface ExecutionContext {
  pyodide: any;
  stdoutBuffer: { value: string };
  stderrBuffer: { value: string };
  stdoutDecoder: TextDecoder;
}

/**
 * Clear user-defined globals for a fresh stateful session on this worker.
 * Prevents state from a previous thread's execution bleeding into a new thread
 * that has no prior session bytes.
 */
async function clearGlobals(ctx: ExecutionContext): Promise<void> {
  try {
    ctx.pyodide.setStdout(createSuppressedStdout());
    await ctx.pyodide.runPythonAsync(`
_skip = frozenset({'_skip', 'cloudpickle', 'micropip'})
for _k in [k for k in list(globals()) if not k.startswith('__') and k not in _skip]:
    del globals()[_k]
globals().pop('_k', None)
`);
  } catch (e: unknown) {
    ctx.stderrBuffer.value += `Global clear error: ${errorToString(e)}\n`;
  } finally {
    ctx.pyodide.setStdout(createStdoutHandler(ctx.stdoutBuffer, ctx.stdoutDecoder));
  }
}

/**
 * Try to restore session, logging errors to stderr
 */
async function tryRestoreSession(ctx: ExecutionContext, sessionBytes: number[]): Promise<void> {
  try {
    ctx.pyodide.setStdout(createSuppressedStdout());
    await restoreSession(ctx.pyodide, sessionBytes);
  } catch (e: unknown) {
    ctx.stderrBuffer.value += `Session restore error: ${errorToString(e)}\n`;
  } finally {
    ctx.pyodide.setStdout(createStdoutHandler(ctx.stdoutBuffer, ctx.stdoutDecoder));
  }
}

/**
 * Mount files and invalidate import cache
 */
async function mountAndInvalidateCache(ctx: ExecutionContext, files: Record<string, number[]>): Promise<void> {
  mountFiles(ctx.pyodide, files);
  ctx.pyodide.setStdout(createSuppressedStdout());
  await ctx.pyodide.runPythonAsync(`import importlib; importlib.invalidate_caches()`);
  ctx.pyodide.setStdout(createStdoutHandler(ctx.stdoutBuffer, ctx.stdoutDecoder));
}

/**
 * Execute Python code and return success status
 */
async function executeCode(ctx: ExecutionContext, code: string): Promise<{ success: boolean; result: unknown }> {
  try {
    const result = await ctx.pyodide.runPythonAsync(code);
    return { success: true, result };
  } catch (e: unknown) {
    ctx.stderrBuffer.value += `${errorToString(e)}\n`;
    return { success: false, result: null };
  }
}

/**
 * Try to save session state, logging errors to stderr
 */
async function trySaveSession(
  ctx: ExecutionContext,
  metadata: Record<string, unknown> | undefined,
): Promise<{ session_bytes?: number[]; session_metadata?: Record<string, unknown> }> {
  try {
    ctx.pyodide.setStdout(createSuppressedStdout());
    await ctx.pyodide.runPythonAsync(`
try:
    import cloudpickle
except ImportError:
    import micropip
    await micropip.install('cloudpickle')
    import cloudpickle
`);
    ctx.pyodide.setStdout(createStdoutHandler(ctx.stdoutBuffer, ctx.stdoutDecoder));

    const session_bytes = await saveSession(ctx.pyodide);
    return {
      session_bytes,
      session_metadata: { ...metadata, last_modified: new Date().toISOString() },
    };
  } catch (e: unknown) {
    ctx.stderrBuffer.value += `Session save error: ${errorToString(e)}\n`;
    ctx.pyodide.setStdout(createStdoutHandler(ctx.stdoutBuffer, ctx.stdoutDecoder));
    return {};
  }
}

/**
 * Collect all changed files from tracking and snapshots
 */
function collectChangedFiles(
  pyodide: any,
  tracker: ReturnType<typeof createFileTracker>,
  beforeSnapshot: Map<string, number>,
): Array<{ path: string; content: number[] }> {
  const allChangedPaths = new Set([...tracker.createdFiles, ...tracker.modifiedFiles]);
  const afterSnapshot = snapshotFiles(pyodide, ["/"]);
  const snapshotChanges = findChangedFiles(beforeSnapshot, afterSnapshot);
  snapshotChanges.forEach((p) => allChangedPaths.add(p));

  if (allChangedPaths.size === 0) return [];

  const changedFiles = collectFilesFromPaths(pyodide, Array.from(allChangedPaths));
  return changedFiles;
}

/**
 * Long-running Pyodide worker
 */
class PyodideWorker {
  private pyodide: any = null;
  private initialized = false;
  private requestCount = 0;

  async initialize(): Promise<void> {
    if (this.initialized) return;

    console.error("[Worker] Loading Pyodide...");
    const start = Date.now();

    this.pyodide = await loadPyodide();
    this.pyodide.setStdout(createSuppressedStdout());
    await this.pyodide.loadPackage("micropip");

    await this.pyodide.runPythonAsync(`
import os
import sys
if 'matplotlib' not in sys.modules:
    os.environ['MPLBACKEND'] = 'Agg'
`);

    this.initialized = true;
    console.error(`[Worker] Ready in ${Date.now() - start}ms (PID: ${Deno.pid})`);
  }

  async execute(params: ExecuteRequest): Promise<ExecuteResult> {
    const startTime = Date.now();
    this.requestCount++;

    const ctx: ExecutionContext = {
      pyodide: this.pyodide,
      stdoutBuffer: { value: "" },
      stderrBuffer: { value: "" },
      stdoutDecoder: new TextDecoder(),
    };

    try {
      this.pyodide.setStdout(createStdoutHandler(ctx.stdoutBuffer, ctx.stdoutDecoder));
      this.pyodide.setStderr(createStdoutHandler(ctx.stderrBuffer, new TextDecoder()));

      // Restore session if needed (or clear globals for fresh stateful session)
      if (params.stateful) {
        if (params.session_bytes) {
          await tryRestoreSession(ctx, params.session_bytes);
        } else {
          // No prior session bytes — clear globals so a fresh thread does not
          // inherit state left behind by a previous thread on this worker.
          await clearGlobals(ctx);
        }
      }

      // Mount files if provided
      if (params.files) {
        await mountAndInvalidateCache(ctx, params.files);
      }

      // Set up file tracking
      const tracker = createFileTracker();
      const beforeSnapshot = snapshotFiles(this.pyodide, ["/tmp", "/home"]);
      this.pyodide.FS.trackingDelegate = tracker.delegate;

      // Execute code
      const { success, result: execResult } = await executeCode(ctx, params.code);
      this.pyodide.FS.trackingDelegate = {};

      // Build result
      const result: ExecuteResult = {
        success,
        result: execResult,
        stdout: filterMicropipMessages(ctx.stdoutBuffer.value),
        stderr: ctx.stderrBuffer.value,
        execution_time_ms: Date.now() - startTime,
      };

      // Save session if needed
      if (params.stateful && success) {
        const sessionData = await trySaveSession(ctx, params.session_metadata);
        result.session_bytes = sessionData.session_bytes;
        result.session_metadata = sessionData.session_metadata;
        result.stderr = ctx.stderrBuffer.value; // Update in case of save error
      }

      // Collect changed files
      result.created_files = collectChangedFiles(this.pyodide, tracker, beforeSnapshot);

      // Return full file list for deletion detection
      if (params.stateful) {
        const finalSnapshot = snapshotFiles(this.pyodide, ["/tmp", "/home"]);
        const finalFilesRecord: Record<string, number[]> = {};
        const collected = collectFilesFromPaths(this.pyodide, Array.from(finalSnapshot.keys()));
        for (const fileObj of collected) {
          finalFilesRecord[fileObj.path] = fileObj.content;
        }
        result.files = finalFilesRecord;
      }

      return result;
    } catch (e: unknown) {
      return {
        success: false,
        stdout: "",
        stderr: `Execution error: ${errorToString(e)}\n`,
        result: null,
        execution_time_ms: Date.now() - startTime,
      };
    }
  }

  async handleRequest(request: JsonRpcRequest): Promise<JsonRpcResponse> {
    const { id, method, params } = request;

    try {
      if (method === "execute") {
        const result = await this.execute(params as ExecuteRequest);
        return { jsonrpc: "2.0", id, result };
      } else if (method === "health") {
        return {
          jsonrpc: "2.0",
          id,
          result: {
            status: "healthy",
            request_count: this.requestCount,
            uptime_ms: Date.now() - START_TIME,
            pid: Deno.pid,
          },
        };
      } else if (method === "shutdown") {
        return {
          jsonrpc: "2.0",
          id,
          result: { status: "shutting_down" },
        };
      } else {
        throw new Error(`Unknown method: ${method}`);
      }
    } catch (error) {
      return {
        jsonrpc: "2.0",
        id,
        error: {
          code: -32603,
          message: String(error),
        },
      };
    }
  }

  async run(): Promise<void> {
    await this.initialize();

    // Read JSON-RPC requests from stdin line-by-line
    const decoder = new TextDecoder();
    const buffer = new Uint8Array(65536);
    let leftover = "";

    while (true) {
      const bytesRead = await Deno.stdin.read(buffer);
      if (bytesRead === null) break;

      const chunk = decoder.decode(buffer.subarray(0, bytesRead));
      const lines = (leftover + chunk).split("\n");
      leftover = lines.pop() || "";

      for (const line of lines) {
        if (!line.trim()) continue;

        try {
          const request = JSON.parse(line) as JsonRpcRequest;
          const response = await this.handleRequest(request);

          // Check for shutdown
          if (request.method === "shutdown") {
            await Deno.stdout.write(
              new TextEncoder().encode(JSON.stringify(response) + "\n"),
            );
            Deno.exit(0);
          }

          // Write response to stdout
          await Deno.stdout.write(
            new TextEncoder().encode(JSON.stringify(response) + "\n"),
          );
        } catch (error) {
          console.error(`[Worker] Error processing request:`, error);
          // Send JSON-RPC error response for malformed requests
          const errorResponse = {
            jsonrpc: "2.0",
            id: null,
            error: { code: -32700, message: `Parse error: ${error}` }
          };
          await Deno.stdout.write(
            new TextEncoder().encode(JSON.stringify(errorResponse) + "\n"),
          );
        }
      }
    }
  }
}

// Start worker
if (import.meta.main) {
  const worker = new PyodideWorker();
  await worker.run();
}
