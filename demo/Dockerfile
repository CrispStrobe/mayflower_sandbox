# Mayflower Sandbox Demo — Docker image
#
# Build (from repo root):
#   docker build -f demo/Dockerfile -t mayflower-demo .
#
# Run locally:
#   docker run -p 7860:7860 -e API_KEY=sk-... mayflower-demo
#
# HF Spaces (Docker SDK):
#   Copy this file to the repo root as "Dockerfile" and push to your Space.
#   Set API_KEY, API_URL, DEFAULT_MODEL as Space Secrets.

FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        unzip \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Deno (required by the sandbox worker) ─────────────────────────────────────
# Install to /usr/local so deno binary lands in /usr/local/bin (already in PATH)
ENV DENO_INSTALL=/usr/local
RUN curl -fsSL https://deno.land/install.sh | sh -s -- --no-modify-path \
    && deno --version

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app

# Cache busting: install heavy deps before copying full source
COPY demo/requirements.txt ./demo/requirements.txt
RUN pip install --no-cache-dir -r demo/requirements.txt

# Install the sandbox package from source
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

# Copy the demo app (and anything else needed at runtime)
COPY demo/app.py ./demo/app.py

# ── Runtime environment ────────────────────────────────────────────────────────
ENV MAYFLOWER_USE_SQLITE=true
ENV MAYFLOWER_DB_PATH=/tmp/mayflower_demo.db
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# HF Spaces exposes 7860
EXPOSE 7860

CMD ["python", "demo/app.py"]
