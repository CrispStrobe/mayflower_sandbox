import asyncio
import json
import os
import tempfile
import uuid
import logging
import sys
from pathlib import Path
from typing import Any, cast

import gradio as gr
import httpx
from dotenv import load_dotenv
from openai import AsyncOpenAI

# ── Load environment variables ────────────────────────────────────────────────
load_dotenv()

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
    from config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_PROVIDER, PROVIDERS as CONFIG_PROVIDERS
except ImportError:
    try:
        from demo.config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_PROVIDER, PROVIDERS as CONFIG_PROVIDERS
    except ImportError:
        from .config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_PROVIDER, PROVIDERS as CONFIG_PROVIDERS

# ── Providers and Models ─────────────────────────────────────────────────────
# Merge CONFIG_PROVIDERS and ensure Ollama is present as a fallback
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

    # Use base_url from config
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
        # Standard OpenAI-compatible /models response format
        for item in data.get("data", []):
            model_id = item.get("id")
            if not model_id:
                continue
            models.append(model_id)

        return sorted(models)
    except Exception as e:
        logger.error(f"Error fetching models for {provider_name}: {e}")
        # Fallback to predefined models in config if fetch fails
        return config.get("chat_models", []) or config.get("vision_models", [])


# ── Tool definitions (OpenAI function-calling format) ─────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Execute Python code in a persistent, stateful sandbox. "
                "Variables and installed packages persist between calls within the same session. "
                "External packages: `import micropip; await micropip.install(['numpy', 'pandas'])`. "
                "Plots: use `matplotlib.use('Agg')`, save with `plt.savefig('/home/plot.png')` — "
                "images in /home/ are displayed automatically after each call."
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
1. Persistence: Variables AND files (/home, /tmp, /site-packages) persist between calls and conversation turns in the same session.
2. Packages: Most common packages (numpy, matplotlib, pandas) are pre-installed.
   If you need others, you MUST use `import micropip; await micropip.install('package_name')`.
   IMPORTANT: You MUST `await` the install call.
3. Plotting: Always use `matplotlib.use('Agg')` BEFORE importing `plt`.
   Save plots to `/home/plot.png`. Images saved in `/home` are automatically shown to the user.
4. Shell: You have a BusyBox shell. Use it for file management or system tasks.
5. Files: You can create a file in one turn and read it in the next.

Style: Be direct. Execute code immediately when asked.
Do not ask clarifying questions when the intent is clear."""

# ── Execution helpers ──────────────────────────────────────────────────────────
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_DOWNLOAD_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".pdf", ".csv", ".docx", ".xlsx", ".pptx", ".txt", ".json", ".md"
}
# session_id → path → last_seen_mtime
_last_mtimes: dict[str, dict[str, str]] = {}


async def _run_tool(
    backend: MayflowerSandboxBackend,
    session_id: str,
    name: str,
    args: dict,
) -> tuple[str, list[tuple[str, bytes]]]:
    """Execute one tool call. Returns (output_text, [(path, bytes), ...])."""
    logger.info(f"Tool execution: {name}({json.dumps(args)})")
    
    if name == "run_python":
        result = await backend.aexecute(args.get("code", ""))
    elif name == "shell":
        result = await backend.aexecute(args.get("command", ""))
    else:
        return f"Unknown tool: {name}", []

    icon = "✅" if result.exit_code == 0 else "❌"
    text = f"{icon} exit={result.exit_code}\n{result.output or '(no output)'}"
    if result.truncated:
        text += "\n… (output truncated)"

    # Collect files from /home/ that are new or updated
    last_seen = _last_mtimes.setdefault(session_id, {})
    new_files: list[tuple[str, bytes]] = []
    try:
        vfs_files = await backend.als_info("/home")
        target_paths = []
        logger.info(f"Scanning /home for session {session_id}. Found {len(vfs_files)} entries.")
        
        for f in vfs_files:
            # Handle both object (FileInfo) and dict formats robustly
            is_dir = f.is_dir if hasattr(f, "is_dir") else f.get("is_dir", False)
            path = f.path if hasattr(f, "path") else f.get("path", "")
            modified_at = f.modified_at if hasattr(f, "modified_at") else f.get("modified_at", "")

            if is_dir:
                continue
            suffix = Path(path).suffix.lower()
            if suffix not in _DOWNLOAD_EXTS:
                continue

            # Show if never seen before, or if modified since last seen
            if path not in last_seen or modified_at != last_seen[path]:
                logger.info(f"New/updated file detected: {path} (mtime: {modified_at})")
                target_paths.append(path)
                last_seen[path] = modified_at
            else:
                logger.debug(f"Skipping unchanged file: {f.path}")

        if target_paths:
            logger.info(f"Downloading {len(target_paths)} files: {target_paths}")
            for dl in await backend.adownload_files(target_paths):
                if dl.content:
                    logger.info(f"Successfully downloaded {dl.path} ({len(dl.content)} bytes)")
                    new_files.append((dl.path, dl.content))
                else:
                    logger.warning(f"File {dl.path} had empty content on download.")
    except Exception as e:
        logger.exception(f"Error during VFS scan/download: {e}")

    return text, new_files


def _save_tmp(data: bytes, suffix: str = ".png") -> str:
    """Persist bytes to a temp file; return its path for Gradio to serve."""
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

    logger.info(f"New user message: {user_msg} (session: {session_id}, model: {model})")

    pool = await _get_pool()
    backend = MayflowerSandboxBackend(
        pool,
        thread_id=session_id,
        allow_net=True,
        stateful=True,
        timeout_seconds=120.0,
    )
    client = AsyncOpenAI(
        base_url=(api_url or "http://localhost:11434/v1").rstrip("/"),
        api_key=api_key or "ollama",
    )

    # Build LLM context from history (dict format)
    llm_msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        if isinstance(m.get("content"), str):
            llm_msgs.append({"role": m["role"], "content": m["content"]})
    llm_msgs.append({"role": "user", "content": user_msg})

    history = list(history) + [{"role": "user", "content": user_msg}]
    yield history, session_id

    for _iteration in range(20):  # hard cap on agentic loop depth
        # ── Stream one LLM turn ────────────────────────────────────────────
        text_acc = ""
        tc_acc: dict[int, dict] = {}
        stream_msg_idx: int | None = None

        logger.info(f"Starting LLM iteration {_iteration}")
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
            logger.error(f"OpenAI API error: {exc}")
            history = list(history)
            history.append({"role": "assistant", "content": f"❌ **API error:** {exc}"})
            yield history, session_id
            return

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                text_acc += delta.content
                history = list(history)
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
            logger.info("LLM finished response (no tool calls).")
            break

        # ── Build the assistant tool-call message ──────────────────────────
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

        # ── Execute each tool and feed result back ─────────────────────────
        for tc in tc_list:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}

            snippet = args.get("code") or args.get("command", "")
            lang = "python" if name == "run_python" else "bash"
            label = "🐍 Python" if name == "run_python" else "🐚 Shell"

            pending = f"{label}\n```{lang}\n{snippet}\n```\n*⏳ running…*"
            history = list(history)
            history.append({"role": "assistant", "content": pending})
            tool_idx = len(history) - 1
            yield history, session_id

            output_text, new_files = await _run_tool(backend, session_id, name, args)

            history = list(history)
            history[tool_idx]["content"] = f"{label}\n```{lang}\n{snippet}\n```\n```\n{output_text}\n```"
            yield history, session_id

            if new_files:
                logger.info(f"Adding {len(new_files)} new files to chat history.")
            for file_path, file_bytes in new_files:
                ext = Path(file_path).suffix.lower()
                tmp = _save_tmp(file_bytes, suffix=ext)
                filename = Path(file_path).name
                logger.info(f"Appeding FileData for {filename} (tmp path: {tmp})")
                history = list(history)
                history.append({"role": "assistant", "content": gr.FileData(path=tmp, orig_name=filename)})
                yield history, session_id

            llm_msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": output_text})

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
    "Generate the first 20 Fibonacci numbers and print them as a formatted table.",
    "Write a CSV with 5 rows of sales data to /home/sales.csv, then use shell to wc -l it.",
    "Install pandas, create a small DataFrame, compute group-by stats, print the result.",
]

_CSS = """
footer { display: none !important; }
"""


def update_provider_settings(provider_name):
    config = PROVIDERS.get(provider_name, PROVIDERS["Ollama"])
    url = config["base_url"]
    key = os.getenv(config["key_name"] + "_API_KEY", "") if config.get("key_name") else ""
    badge = config.get("badge", "")
    # Update model dropdown choices based on config
    models = config.get("chat_models", []) or config.get("vision_models", [])
    model_val = models[0] if models else None
    return url, key, badge, gr.Dropdown(choices=models, value=model_val)


async def get_models_for_ui(provider_name, api_key):
    models = await fetch_models(provider_name, api_key)
    if not models:
        return gr.Dropdown(choices=[], value=None, label="Model (No models found)")
    return gr.Dropdown(choices=models, value=models[0] if models else None, label="Model")


# Gradio 6: css/theme moved from Blocks() to launch()
with gr.Blocks(title="Mayflower Sandbox") as demo:
    session_id = gr.State()
    demo.load(fn=lambda: str(uuid.uuid4()), outputs=session_id)

    gr.Markdown(
        "# 🧪 Mayflower Sandbox\n"
        "Chat with an LLM that executes real Python and shell commands.\n"
        "Plots are shown inline. State persists across calls within a session."
    )

    with gr.Row(equal_height=False):
        # ── Chat column ───────────────────────────────────────────────────────
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(
                height=560,
                show_label=False,
                render_markdown=True,
                layout="bubble",
            )
            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder="Ask me to compute, visualise, or run something…",
                    lines=1,
                    scale=5,
                    show_label=False,
                )
                send_btn = gr.Button("Send ▶", variant="primary", scale=1, min_width=90)
            clear_btn = gr.Button("🗑 New session", size="sm", variant="secondary")
            gr.Examples(examples=_EXAMPLES, inputs=msg_input, label="Try an example")

        # ── Config column ─────────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=230):
            gr.Markdown("### ⚙️ LLM")
            provider_in = gr.Dropdown(
                choices=list(PROVIDERS.keys()),
                value=_DEFAULT_PROVIDER,
                label="Provider",
            )
            badge_info = gr.HTML(value=_DEFAULT_CONFIG.get("badge", ""))

            api_url_in = gr.Textbox(label="API URL", value=_DEFAULT_API_URL)
            api_key_in = gr.Textbox(label="API Key", value=_DEFAULT_API_KEY, type="password")

            with gr.Row():
                fetch_btn = gr.Button("🔄 Fetch Models", size="sm")

            model_in = gr.Dropdown(
                choices=_DEFAULT_CONFIG.get("chat_models", [_DEFAULT_MODEL]),
                value=_DEFAULT_MODEL,
                label="Model",
                allow_custom_value=True,
            )

            gr.Markdown(
                "---\n"
                "⚠️ Model must support **tool/function calling**."
            )

    # ── Event handlers ─────────────────────────────────────────────────────────
    provider_in.change(
        update_provider_settings,
        inputs=[provider_in],
        outputs=[api_url_in, api_key_in, badge_info, model_in],
    )

    fetch_btn.click(
        get_models_for_ui,
        inputs=[provider_in, api_key_in],
        outputs=[model_in],
    )

    _inputs = [msg_input, chatbot, session_id, api_url_in, api_key_in, model_in]
    _outputs = [chatbot, session_id]

    msg_input.submit(respond, _inputs, _outputs).then(lambda: "", outputs=msg_input)
    send_btn.click(respond, _inputs, _outputs).then(lambda: "", outputs=msg_input)

    def _new_session():
        new_id = str(uuid.uuid4())
        _last_mtimes.pop(new_id, None)
        return [], new_id

    clear_btn.click(_new_session, outputs=[chatbot, session_id])


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",  # nosec B104
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
        theme=gr.themes.Soft(),
        css=_CSS,
    )
