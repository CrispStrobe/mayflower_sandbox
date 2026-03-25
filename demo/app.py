import asyncio
import json
import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any, cast

import gradio as gr
import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

# Set pool size to 1 for demo stability/noise reduction
os.environ.setdefault("PYODIDE_POOL_SIZE", "1")

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("mayflower_demo")

# ── Sandbox setup ──────────────────────────────────────────────────────────────
os.environ.setdefault("MAYFLOWER_USE_SQLITE", "true")

from mayflower_sandbox.db import create_sqlite_pool  # type: ignore # noqa: E402
from mayflower_sandbox.deepagents_backend import (  # type: ignore # noqa: E402
    MayflowerSandboxBackend,
)
from mayflower_sandbox.sandbox_executor import ExecutionResult  # type: ignore # noqa: E402

_DB_PATH = os.getenv("MAYFLOWER_DB_PATH", "/tmp/mayflower_demo.db")  # nosec B108
_pool: Any = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> Any:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await create_sqlite_pool(_DB_PATH)
    return _pool


try:
    from config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_PROVIDER
    from config import PROVIDERS as CONFIG_PROVIDERS
except ImportError:
    try:
        from demo.config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_PROVIDER
        from demo.config import PROVIDERS as CONFIG_PROVIDERS
    except ImportError:
        from .config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_PROVIDER
        from .config import PROVIDERS as CONFIG_PROVIDERS

# ── Providers and Models ─────────────────────────────────────────────────────
PROVIDERS: dict[str, dict[str, Any]] = cast("dict[str, dict[str, Any]]", CONFIG_PROVIDERS.copy())
if "Ollama" not in PROVIDERS:
    PROVIDERS["Ollama"] = {
        "base_url": "http://localhost:11434/v1",
        "key_name": "OLLAMA",
        "chat_models": ["llama3.2:3b", "llama3.1:8b"],
        "badge": "🏠 <b>Local</b>",
    }


async def fetch_models(provider_name: str, api_key: str | None) -> list[str]:
    """Fetch models from the selected provider's /models endpoint."""
    config = PROVIDERS.get(provider_name)
    if not config:
        return []

    url = config["base_url"].rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

        models = []
        for item in data.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            models.append(model_id)

        return sorted(models)
    except Exception as e:
        logger.error(f"Error fetching models for {provider_name}: {e}")
        return config.get("chat_models", []) or config.get("vision_models", [])


# ── Tool definitions (OpenAI function-calling format) ─────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python code in a persistent, stateful sandbox. "
                "Variables AND files AND installed packages (/site-packages) persist between calls. "
                "External packages: `import micropip; await micropip.install(['numpy', 'pandas'])`. "
                "Plots: use `matplotlib.use('Agg')` BEFORE importing `plt`. Save to `/home/plot.png`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": (
                "Run a BusyBox shell command. "
                "Supports: ls, cat, grep, wc, echo, mkdir, rm, sed, awk, pipes (|), &&."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                },
                "required": ["command"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a helpful AI assistant with direct access to a Python sandbox and a shell.

Python Sandbox Rules:
1. Persistence: Variables, installed packages (/site-packages), and files (/home, /tmp) persist between calls and conversation turns.
2. Packages: numpy, matplotlib, and pandas are pre-installed. Others: `import micropip; await micropip.install('pkg')`.
3. Plotting: Always use `matplotlib.use('Agg')` BEFORE importing `plt`. Save to `/home/plot.png`.
4. Shell: Use BusyBox for file/system tasks. Files in /home persist.
5. Memory: Sandbox has limited memory (approx 512MB heap). Avoid storing massive datasets in global variables.
   Process data in chunks or save to files if necessary.
   Large variables (>2MB) are automatically skipped during state saving to prevent MemoryErrors.

Style: Be direct. Execute code immediately. Do not ask for permission."""

# ── Execution helpers ──────────────────────────────────────────────────────────
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_DOWNLOAD_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".csv", ".docx", ".xlsx", ".pptx", ".txt", ".json", ".md"
}
_last_mtimes: dict[str, dict[str, str]] = {}


async def _run_tool(
    backend: MayflowerSandboxBackend,
    session_id: str,
    name: str,
    args: dict,
) -> tuple[ExecutionResult, list[tuple[str, bytes]]]:
    """Execute one tool call. Returns (raw_result, [(path, bytes), ...])."""
    logger.info(f"Tool execution: {name}({json.dumps(args)})")

    if name == "run_python":
        result = await backend._executor.execute(args.get("code", ""))
    elif name == "shell":
        result = await backend._executor.execute_shell(args.get("command", ""))
    else:
        raise ValueError(f"Unknown tool: {name}")

    # Collect files from /home/ that are new or updated
    last_seen = _last_mtimes.setdefault(session_id, {})
    new_files: list[tuple[str, bytes]] = []
    try:
        vfs_files = await backend.als_info("/home")
        target_paths = []

        for f in vfs_files:
            # Robust attribute access
            is_dir = f.is_dir if hasattr(f, "is_dir") else f.get("is_dir", False)
            path = f.path if hasattr(f, "path") else f.get("path", "")
            modified_at = f.modified_at if hasattr(f, "modified_at") else f.get("modified_at", "")

            if is_dir:
                continue
            if Path(path).suffix.lower() not in _DOWNLOAD_EXTS:
                continue

            if path not in last_seen or modified_at != last_seen[path]:
                logger.info(f"New/updated file: {path} (mtime: {modified_at})")
                target_paths.append(path)
                last_seen[path] = modified_at

        if target_paths:
            for dl in await backend.adownload_files(target_paths):
                if dl.content:
                    new_files.append((dl.path, dl.content))
    except Exception as e:
        logger.error(f"Error scanning VFS: {e}")

    return result, new_files


def _save_tmp(data: bytes, suffix: str = ".png") -> str:
    """Persist bytes to a temp file for Gradio."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        return f.name


# ── Main chat coroutine ────────────────────────────────────────────────────────
async def respond(
    user_msg: str,
    history: list[dict[str, Any]],
    session_id: str,
    api_url: str,
    api_key: str,
    model: str,
):
    """Async generator yielding (history, session_id) on every UI update."""
    if not user_msg.strip():
        yield history, session_id
        return

    logger.info(f"Message from {session_id}: {user_msg[:50]}...")

    pool = await _get_pool()
    backend = MayflowerSandboxBackend(
        pool,
        thread_id=session_id,
        allow_net=True,
        stateful=True,
        timeout_seconds=120.0,
    )
    # Prevent redundant preloading log noise
    backend._executor._helpers_loaded = True

    client = AsyncOpenAI(
        base_url=(api_url or "http://localhost:11434/v1").rstrip("/"),
        api_key=api_key or "ollama",
    )

    llm_msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        if isinstance(m.get("content"), str):
            llm_msgs.append({"role": m["role"], "content": m["content"]})
    llm_msgs.append({"role": "user", "content": user_msg})

    history = list(history) + [{"role": "user", "content": user_msg}]
    yield history, session_id

    for _iteration in range(20):
        text_acc = ""
        tc_acc: dict[int, dict] = {}
        stream_msg_idx: int | None = None

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=llm_msgs,  # type: ignore
                tools=cast("Any", TOOLS),
                tool_choice="auto",
                stream=True,
                max_tokens=4096,
            )
        except Exception as exc:
            history.append({"role": "assistant", "content": f"❌ **API error:** {exc}"})
            yield history, session_id
            return

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                text_acc += delta.content
                if stream_msg_idx is None:
                    history.append({"role": "assistant", "content": text_acc})
                    stream_msg_idx = len(history) - 1
                else:
                    history[stream_msg_idx]["content"] = text_acc
                yield history, session_id

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    i = tc.index
                    if i not in tc_acc:
                        tc_acc[i] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tc_acc[i]["id"] += tc.id
                    if tc.function:
                        if tc.function.name:
                            tc_acc[i]["name"] += tc.function.name
                        if tc.function.arguments:
                            tc_acc[i]["arguments"] += tc.function.arguments

        if text_acc:
            llm_msgs.append({"role": "assistant", "content": text_acc})

        if not tc_acc:
            break

        tc_list = []
        for i in sorted(tc_acc):
            tc = tc_acc[i]
            if not tc["id"]:
                tc["id"] = f"call_{i}_{uuid.uuid4().hex[:8]}"
            tc_list.append(
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
            )

        llm_msgs.append({"role": "assistant", "content": text_acc or None, "tool_calls": tc_list})

        for tc in tc_list:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            snippet = args.get("code") or args.get("command", "")
            lang = "python" if name == "run_python" else "bash"
            label = "🐍 Python" if name == "run_python" else "🐚 Shell"

            history.append({"role": "assistant", "content": f"{label}\n```{lang}\n{snippet}\n```\n*⏳ running…*"})
            tool_idx = len(history) - 1
            yield history, session_id

            # Execute directly via sandbox executor to get the raw ExecutionResult
            result, new_files = await _run_tool(backend, session_id, name, args)

            # Format the display output similar to the user's request
            icon = "✅" if result.success else "❌"
            exit_code = result.exit_code if result.exit_code is not None else (0 if result.success else 1)

            output = result.stdout or ""
            if result.stderr:
                output = f"{output}\n{result.stderr}" if output else result.stderr

            # If there's a result value (expression), include it
            if result.result is not None and not result.stdout:
                res_str = str(result.result)
                output = f"{output}\n{res_str}" if output else res_str

            if not output.strip():
                output = "(no output)"

            history[tool_idx]["content"] = f"{label}\n```{lang}\n{snippet}\n```\n{icon} exit={exit_code}\n```\n{output}\n```"
            yield history, session_id

            for f_path, f_bytes in new_files:
                ext = Path(f_path).suffix.lower()
                tmp = _save_tmp(f_bytes, suffix=ext)
                history.append({"role": "assistant", "content": gr.FileData(path=tmp, orig_name=Path(f_path).name)})
                yield history, session_id

            # For the LLM, we still feed it the combined text output
            combined_text = result.stdout or ""
            if result.stderr:
                combined_text = f"{combined_text}\n{result.stderr}" if combined_text else result.stderr
            if result.result is not None and not result.stdout:
                combined_text = f"{combined_text}\n{result.result}" if combined_text else str(result.result)

            llm_msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": combined_text})

    yield history, session_id


# ── Gradio UI ──────────────────────────────────────────────────────────────────
_DEFAULT_PROVIDER = DEFAULT_CHAT_PROVIDER
_DEFAULT_CONFIG = PROVIDERS.get(_DEFAULT_PROVIDER, PROVIDERS["Ollama"])
_DEFAULT_API_URL = _DEFAULT_CONFIG["base_url"]
_DEFAULT_API_KEY = os.getenv(_DEFAULT_CONFIG["key_name"] + "_API_KEY", "") if _DEFAULT_CONFIG.get("key_name") else ""
_DEFAULT_MODEL = DEFAULT_CHAT_MODEL

_EXAMPLES = [
    "Plot a sine wave with random noise added. Save to /home/plot.png.",
    "Estimate π via Monte Carlo with 200,000 random points (use numpy).",
    "Create a bar chart of the top 5 programming languages by GitHub stars (made-up data is fine).",
]

_CSS = "footer { display: none !important; }"

def update_provider_settings(provider_name):
    config = PROVIDERS.get(provider_name, PROVIDERS["Ollama"])
    models = config.get("chat_models", []) or config.get("vision_models", [])
    return config["base_url"], os.getenv(config["key_name"] + "_API_KEY", ""), config.get("badge", ""), gr.Dropdown(choices=models, value=models[0] if models else None)

async def get_models_for_ui(p, k):
    m = await fetch_models(p, k)
    return gr.Dropdown(choices=m, value=m[0] if m else None, label="Model")

with gr.Blocks(title="Mayflower Sandbox") as demo:
    session_id = gr.State()
    demo.load(fn=lambda: str(uuid.uuid4()), outputs=session_id)

    gr.Markdown("# 🧪 Mayflower Sandbox\nReal Python/Shell execution. Variables and files persist.")

    with gr.Row(equal_height=False):
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(height=560, show_label=False, render_markdown=True, layout="bubble")
            with gr.Row():
                msg_input = gr.Textbox(placeholder="Ask me to compute something…", lines=1, scale=5, show_label=False)
                send_btn = gr.Button("Send ▶", variant="primary", scale=1)
            clear_btn = gr.Button("🗑 New session", size="sm", variant="secondary")
            gr.Examples(examples=_EXAMPLES, inputs=msg_input)

        with gr.Column(scale=1, min_width=230):
            gr.Markdown("### ⚙️ LLM")
            provider_in = gr.Dropdown(choices=list(PROVIDERS.keys()), value=_DEFAULT_PROVIDER, label="Provider")
            badge_info = gr.HTML(value=_DEFAULT_CONFIG.get("badge", ""))
            api_url_in = gr.Textbox(label="API URL", value=_DEFAULT_API_URL)
            api_key_in = gr.Textbox(label="API Key", value=_DEFAULT_API_KEY, type="password")
            fetch_btn = gr.Button("🔄 Fetch Models", size="sm")
            model_in = gr.Dropdown(choices=_DEFAULT_CONFIG.get("chat_models", [_DEFAULT_MODEL]), value=_DEFAULT_MODEL, label="Model", allow_custom_value=True)
            gr.Markdown("---\n⚠️ Model must support **tool/function calling**.")

    provider_in.change(update_provider_settings, inputs=[provider_in], outputs=[api_url_in, api_key_in, badge_info, model_in])
    fetch_btn.click(get_models_for_ui, inputs=[provider_in, api_key_in], outputs=[model_in])

    _inputs = [msg_input, chatbot, session_id, api_url_in, api_key_in, model_in]
    msg_input.submit(respond, _inputs, [chatbot, session_id]).then(lambda: "", outputs=msg_input)
    send_btn.click(respond, _inputs, [chatbot, session_id]).then(lambda: "", outputs=msg_input)
    clear_btn.click(lambda: ([], str(uuid.uuid4())), outputs=[chatbot, session_id])

if __name__ == "__main__":
    demo.queue().launch(server_name="0.0.0.0", server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")), show_error=True, theme=gr.themes.Soft(), css=_CSS)
