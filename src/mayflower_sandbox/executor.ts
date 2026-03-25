/**
 * Mayflower Sandbox - Pyodide Executor
 *
 * Clean, minimal Pyodide executor with stdin/stdout protocol.
 * No dependency on langchain-sandbox - written from scratch.
 */

import { loadPyodide } from "npm:pyodide@0.28.3";
import { parseArgs } from "jsr:@std/cli@1.0.23/parse-args";
import { collectFilesFromPaths } from "./fs_utils.ts";
import {
  filterMicropipMessages,
  createStdoutHandler,
  createSuppressedStdout,
  createFileTracker,
} from "./worker_utils.ts";

interface ExecutionOptions {
  code: string;
  files?: Record<string, Uint8Array>;
  stateful?: boolean;
  sessionBytes?: Uint8Array;
  sessionMetadata?: Record<string, unknown>;
}

interface ExecutionResult {
  success: boolean;
  stdout: string;
  stderr: string;
  result: unknown;
  sessionBytes?: number[];
  sessionMetadata?: Record<string, unknown>;
  created_files?: Array<{ path: string; content: number[] }>; // for compatibility
  files?: Record<string, number[]>; // changed to record for host-side easy lookup
}

// Utility functions (filterMicropipMessages, createStdoutHandler, etc.)
// are imported from worker_utils.ts

/**
 * Read binary file data from stdin
 */
async function readStdinFiles(): Promise<Record<string, Uint8Array>> {
  const files: Record<string, Uint8Array> = {};

  // Read all stdin data (modern Deno API)
  const chunks: Uint8Array[] = [];
  const buffer = new Uint8Array(8192);

  while (true) {
    const bytesRead = await Deno.stdin.read(buffer);
    if (bytesRead === null) break;
    chunks.push(buffer.slice(0, bytesRead));
  }

  const stdinData = new Uint8Array(chunks.reduce((acc, chunk) => acc + chunk.length, 0));
  let offset = 0;
  for (const chunk of chunks) {
    stdinData.set(chunk, offset);
    offset += chunk.length;
  }

  if (stdinData.length === 0) {
    return files;
  }

  // Parse binary protocol: "MFS\x01" + length(4) + JSON metadata + file contents
  const magic = new TextDecoder().decode(stdinData.slice(0, 4));
  if (!magic.startsWith("MFS")) {
    return files;
  }

  const metadataLength = new DataView(stdinData.buffer).getUint32(4, false);
  const metadataBytes = stdinData.slice(8, 8 + metadataLength);
  const metadata = JSON.parse(new TextDecoder().decode(metadataBytes));

  let fileOffset = 8 + metadataLength;

  for (const file of metadata.files || []) {
    const content = stdinData.slice(fileOffset, fileOffset + file.size);
    files[file.path] = content;
    fileOffset += file.size;
  }

  return files;
}

// File operations (snapshotFiles, collectFiles, collectFilesFromPaths)
// are now in fs_utils.ts to reduce duplication and cognitive complexity

/**
 * Restore session state from bytes
 */
async function restoreSession(
  pyodide: any,
  sessionBytes: Uint8Array,
  stdoutBuffer: { value: string },
  stderrBuffer: { value: string },
  stdoutDecoder: TextDecoder,
): Promise<void> {
  pyodide.setStdout(createSuppressedStdout());

  await pyodide.runPythonAsync(`
try:
    import cloudpickle
except ImportError:
    import micropip
    await micropip.install('cloudpickle')
    import cloudpickle
`);

  pyodide.setStdout(createStdoutHandler(stdoutBuffer, stdoutDecoder));

  await pyodide.runPythonAsync(`
import micropip

_session_bytes = bytes(${JSON.stringify(Array.from(sessionBytes))})

# Pre-install common modules often found in pickled sessions
for _m in ['numpy', 'matplotlib', 'pandas']:
    try:
        import importlib
        importlib.import_module(_m)
    except ImportError:
        await micropip.install(_m)

# Attempt to load the session, installing missing modules as needed
for _retry in range(5):  # hard cap on recursive dependency resolution
    try:
        _session_obj = cloudpickle.loads(_session_bytes)
        break
    except (ModuleNotFoundError, Exception) as e:
        if hasattr(e, 'name') and e.name:
            _pkg = e.name.split('.')[0]
            await micropip.install(_pkg)
        else:
            raise

globals().update(_session_obj)

# Cleanup helper vars safely
for _v in ['_session_bytes', '_session_obj', '_retry', '_pkg', '_m', 'importlib']:
    globals().pop(_v, None)
del _v
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
    _session_dict[k] = v
list(cloudpickle.dumps(_session_dict))
`);
  return sessionBytesResult.toJs();
}

/**
 * Mount files to Pyodide filesystem
 */
async function mountFiles(
  pyodide: any,
  files: Record<string, Uint8Array>,
): Promise<void> {
  for (const [path, content] of Object.entries(files)) {
    const dir = path.substring(0, path.lastIndexOf("/"));
    if (dir && dir !== "/") {
      pyodide.FS.mkdirTree(dir);
    }
    pyodide.FS.writeFile(path, content);
  }

  await pyodide.runPythonAsync(`
import importlib
importlib.invalidate_caches()
`);
}

/**
 * Configure matplotlib and pre-install common packages
 */
async function configureEnvironment(pyodide: any): Promise<void> {
  try {
    await pyodide.runPythonAsync(`
import os
import sys
import micropip

# Configure matplotlib for non-interactive backend
os.environ['MPLBACKEND'] = 'Agg'

# Pre-install common modules
await micropip.install(['numpy', 'matplotlib', 'pandas'])
`);
  } catch {
    // environment config failed - not critical, continue anyway
  }
}

/**
 * Execute Python code in Pyodide
 */
async function execute(options: ExecutionOptions): Promise<ExecutionResult> {
  const result: ExecutionResult = {
    success: false,
    stdout: "",
    stderr: "",
    result: null,
  };

  try {
    const pyodide = await loadPyodide();
    await pyodide.loadPackage("micropip");

    const stdoutBuffer = { value: "" };
    const stderrBuffer = { value: "" };
    const stdoutDecoder = new TextDecoder();
    const stderrDecoder = new TextDecoder();

    pyodide.setStdout(createStdoutHandler(stdoutBuffer, stdoutDecoder));
    pyodide.setStderr(createStdoutHandler(stderrBuffer, stderrDecoder));

    // Restore session if stateful
    if (options.stateful && options.sessionBytes) {
      try {
        await restoreSession(pyodide, options.sessionBytes, stdoutBuffer, stderrBuffer, stdoutDecoder);
      } catch (e) {
        stderrBuffer.value += `Session restore error: ${e}\n`;
        pyodide.setStdout(createStdoutHandler(stdoutBuffer, stdoutDecoder));
      }
    }

    // Mount files
    if (options.files) {
      await mountFiles(pyodide, options.files);
    }

    await configureEnvironment(pyodide);

    // Track file operations
    const tracker = createFileTracker();
    pyodide.FS.trackingDelegate = tracker.delegate;

    // Execute code
    try {
      result.result = await pyodide.runPythonAsync(options.code);
      result.success = true;
    } catch (e) {
      stderrBuffer.value += `${e}\n`;
    }

    pyodide.FS.trackingDelegate = {};

    result.stdout = filterMicropipMessages(stdoutBuffer.value);
    result.stderr = stderrBuffer.value;

    // Save session if stateful and successful
    if (options.stateful && result.success) {
      try {
        pyodide.setStdout(createSuppressedStdout());
        await pyodide.runPythonAsync(`
try:
    import cloudpickle
except ImportError:
    import micropip
    await micropip.install('cloudpickle')
    import cloudpickle
`);
        pyodide.setStdout(createStdoutHandler(stdoutBuffer, stdoutDecoder));

        result.sessionBytes = await saveSession(pyodide);
        result.sessionMetadata = {
          ...options.sessionMetadata,
          lastModified: new Date().toISOString(),
        };
      } catch (e) {
        stderrBuffer.value += `Session save error: ${e}\n`;
        result.stderr = stderrBuffer.value;
        pyodide.setStdout(createStdoutHandler(stdoutBuffer, stdoutDecoder));
      }
    }

    // Collect changed files
    const allChangedPaths = new Set([...tracker.createdFiles, ...tracker.modifiedFiles]);
    result.created_files = collectFilesFromPaths(pyodide, Array.from(allChangedPaths));

    // Return full file list for deletion detection
    if (options.stateful) {
      const { snapshotFiles } = await import("./fs_utils.ts");
      const finalSnapshot = snapshotFiles(pyodide, ["/tmp", "/home", "/site-packages"]);
      const finalFilesRecord: Record<string, number[]> = {};
      const collected = collectFilesFromPaths(pyodide, Array.from(finalSnapshot.keys()));
      for (const fileObj of collected) {
        finalFilesRecord[fileObj.path] = fileObj.content;
      }
      result.files = finalFilesRecord;
    }

    return result;
  } catch (e) {
    result.stderr += `Execution error: ${e}\n`;
    return result;
  }
}

/**
 * Main entry point
 */
async function main() {
  const args = parseArgs(Deno.args, {
    string: ["code", "session-bytes", "session-metadata"],
    boolean: ["stateful"],
    alias: {
      c: "code",
      s: "stateful",
      b: "session-bytes",
      m: "session-metadata",
    },
  });

  if (!args.code) {
    console.error("Usage: executor.ts -c <code> [-s] [-b <session-bytes>]");
    Deno.exit(1);
  }

  // Read files from stdin
  const files = await readStdinFiles();

  // Parse session data
  let sessionBytes: Uint8Array | undefined;
  let sessionMetadata: Record<string, unknown> | undefined;

  if (args["session-bytes"]) {
    sessionBytes = new Uint8Array(JSON.parse(args["session-bytes"]));
  }

  if (args["session-metadata"]) {
    sessionMetadata = JSON.parse(args["session-metadata"]);
  }

  // Execute
  const result = await execute({
    code: args.code,
    files,
    stateful: args.stateful || false,
    sessionBytes,
    sessionMetadata,
  });

  // Output result as JSON
  console.log(JSON.stringify(result));
}

if (import.meta.main) {
  main();
}
