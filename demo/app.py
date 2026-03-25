"""
Mayflower Sandbox — Gradio Demo
An LLM chatbot with real Python/shell execution via the Mayflower sandbox.

Local usage:
    pip install -e ".[demo]"
    python demo/app.py

Docker / HF Spaces:
    docker build -f demo/Dockerfile -t mayflower-demo .
    docker run -p 7860:7860 -e API_KEY=sk-... mayflower-demo
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from pathlib import Path

import gradio as gr
from openai import AsyncOpenAI

# ── Sandbox setup ──────────────────────────────────────────────────────────────
os.environ.setdefault("MAYFLOWER_USE_SQLITE", "true")

from mayflower_sandbox.db import create_sqlite_pool  # noqa: E402
from mayflower_sandbox.deepagents_backend import MayflowerSandboxBackend  # noqa: E402

_DB_PATH = os.getenv("MAYFLOWER_DB_PATH", "/tmp/mayflower_demo.db")
_pool: object | None = None
_pool_lock = asyncio.Lock()


async def _get_pool() -> object:
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await create_sqlite_pool(_DB_PATH)
    return _pool


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

Capabilities:
- run_python: stateful Python execution. Variables persist between calls in the same session.
  Install packages: `import micropip; await micropip.install(['numpy', 'matplotlib'])`
  For plots: always call `matplotlib.use('Agg')` first, then `plt.savefig('/home/plot.png')`.
  Images saved to /home/ are shown automatically — no need to display them manually.
- shell: BusyBox shell (ls, cat, grep, wc, echo, mkdir, rm, sed, awk, pipes, &&).

Style: Be direct. When asked to compute or visualise something, do it immediately with the tools.
Do not ask clarifying questions when the intent is clear."""

# ── Execution helpers ──────────────────────────────────────────────────────────
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_seen_images: dict[str, set[str]] = {}  # session_id → paths already shown


async def _run_tool(
    backend: MayflowerSandboxBackend,
    session_id: str,
    name: str,
    args: dict,
) -> tuple[str, list[tuple[str, bytes]]]:
    """Execute one tool call. Returns (output_text, [(path, bytes), ...])."""
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

    # Collect new image files from /home/ (only ones not yet shown)
    seen = _seen_images.setdefault(session_id, set())
    new_images: list[tuple[str, bytes]] = []
    try:
        vfs_files = await backend.als_info("/home")
        img_paths = [
            f.path
            for f in vfs_files
            if not f.is_dir and Path(f.path).suffix.lower() in _IMAGE_EXTS and f.path not in seen
        ]
        if img_paths:
            for dl in await backend.adownload_files(img_paths):
                if dl.content:
                    seen.add(dl.path)
                    new_images.append((dl.path, dl.content))
    except Exception:  # noqa: S110  # nosec B110 — VFS scan is best-effort
        pass

    return text, new_images


def _save_tmp(data: bytes, suffix: str = ".png") -> str:
    """Persist bytes to a temp file; return its path for Gradio to serve."""
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        return f.name


# ── Main chat coroutine ────────────────────────────────────────────────────────
async def respond(
    user_msg: str,
    history: list[dict],
    session_id: str,
    api_url: str,
    api_key: str,
    model: str,
):
    """Async generator yielding (history, session_id) on every UI update."""
    if not user_msg.strip():
        yield history, session_id
        return

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

    # Build LLM context from history (text only — images are display-only)
    llm_msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in history:
        if m["role"] in ("user", "assistant") and isinstance(m.get("content"), str):
            llm_msgs.append({"role": m["role"], "content": m["content"]})
    llm_msgs.append({"role": "user", "content": user_msg})

    history = list(history) + [{"role": "user", "content": user_msg}]
    yield history, session_id

    for _iteration in range(20):  # hard cap on agentic loop depth
        # ── Stream one LLM turn ────────────────────────────────────────────
        text_acc = ""
        tc_acc: dict[int, dict] = {}
        stream_msg_idx: int | None = None

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=llm_msgs,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
                max_tokens=4096,
            )
        except Exception as exc:
            history = history + [{"role": "assistant", "content": f"❌ **API error:** {exc}"}]
            yield history, session_id
            return

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            # Accumulate streamed text and update the last assistant bubble
            if delta.content:
                text_acc += delta.content
                if stream_msg_idx is None:
                    history = history + [{"role": "assistant", "content": text_acc}]
                    stream_msg_idx = len(history) - 1
                else:
                    history = list(history)
                    history[stream_msg_idx] = {"role": "assistant", "content": text_acc}
                yield history, session_id

            # Accumulate tool call chunks (may arrive across many chunks)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    i = tc.index
                    if i not in tc_acc:
                        tc_acc[i] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        tc_acc[i]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tc_acc[i]["name"] += tc.function.name
                        if tc.function.arguments:
                            tc_acc[i]["arguments"] += tc.function.arguments

        # Commit text turn to LLM context
        if text_acc:
            llm_msgs.append({"role": "assistant", "content": text_acc})

        # No tool calls → LLM is done
        if not tc_acc:
            break

        # ── Build the assistant tool-call message ──────────────────────────
        tc_list = []
        for i in sorted(tc_acc):
            tc = tc_acc[i]
            if not tc["id"]:  # some models omit IDs
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

            # Show "running…" placeholder
            pending = f"{label}\n```{lang}\n{snippet}\n```\n*⏳ running…*"
            history = history + [{"role": "assistant", "content": pending}]
            tool_idx = len(history) - 1
            yield history, session_id

            # Execute in sandbox
            output_text, new_images = await _run_tool(backend, session_id, name, args)

            # Replace placeholder with result
            history = list(history)
            history[tool_idx] = {
                "role": "assistant",
                "content": f"{label}\n```{lang}\n{snippet}\n```\n```\n{output_text}\n```",
            }
            yield history, session_id

            # Append any new images as separate bubbles
            for img_path, img_bytes in new_images:
                tmp = _save_tmp(img_bytes, suffix=Path(img_path).suffix)
                history = history + [{"role": "assistant", "content": {"path": tmp}}]
                yield history, session_id

            # Return tool result to LLM
            llm_msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": output_text})

    yield history, session_id


# ── Gradio UI ──────────────────────────────────────────────────────────────────
_DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:11434/v1")
_DEFAULT_API_KEY = os.getenv("API_KEY", os.getenv("OPENAI_API_KEY", "ollama"))
_DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.2:3b")

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
            api_url_in = gr.Textbox(label="API URL", value=_DEFAULT_API_URL)
            api_key_in = gr.Textbox(label="API Key", value=_DEFAULT_API_KEY, type="password")
            model_in = gr.Textbox(label="Model", value=_DEFAULT_MODEL)
            gr.Markdown(
                "---\n"
                "**Local Ollama**\n"
                "URL: `http://localhost:11434/v1`\n"
                "Model: `llama3.2:3b`\n\n"
                "**OpenAI**\n"
                "URL: `https://api.openai.com/v1`\n"
                "Model: `gpt-4o-mini`\n\n"
                "**HF Inference**\n"
                "URL: `https://api-inference.huggingface.co/v1`\n"
                "Model: `Qwen/Qwen2.5-72B-Instruct`\n\n"
                "⚠️ Model must support **tool/function calling**."
            )

    # ── Event handlers ─────────────────────────────────────────────────────────
    _inputs = [msg_input, chatbot, session_id, api_url_in, api_key_in, model_in]
    _outputs = [chatbot, session_id]

    msg_input.submit(respond, _inputs, _outputs).then(lambda: "", outputs=msg_input)
    send_btn.click(respond, _inputs, _outputs).then(lambda: "", outputs=msg_input)

    def _new_session():
        new_id = str(uuid.uuid4())
        _seen_images.pop(new_id, None)
        return [], new_id

    clear_btn.click(_new_session, outputs=[chatbot, session_id])


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_error=True,
        theme=gr.themes.Soft(),
        css=_CSS,
    )
