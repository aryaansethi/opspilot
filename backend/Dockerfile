# One image for every backend process; choose the process with the command:
#   api (default):   uvicorn app.main:app
#   worker:          python -m app.worker
#   mcp-cloudwatch:  python -m mcp_servers.cloudwatch.server
#   mcp-github:      python -m mcp_servers.github.server
#   scripts:         python /app/scripts/<name>.py  (backend modules importable via PYTHONPATH=/app)
# Build from the repository root (the evaluation dataset is copied in):
#   docker build -f backend/Dockerfile -t opspilot-backend .

FROM ghcr.io/astral-sh/uv:0.11.7 AS uv

FROM python:3.12-slim-bookworm AS build
# Optional cross-encoder reranker (config D). Off by default: PyTorch adds over 1 GB.
ARG INSTALL_RERANK=false
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project $( [ "$INSTALL_RERANK" = "true" ] && echo --group rerank )
COPY backend/ ./
RUN uv sync --frozen --no-dev $( [ "$INSTALL_RERANK" = "true" ] && echo --group rerank )

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 opspilot
WORKDIR /app
COPY --from=build --chown=opspilot:opspilot /app /app
COPY --chown=opspilot:opspilot evaluation/datasets /evaluation/datasets
# Seed/smoke scripts, e.g.: docker compose run --rm api python /app/scripts/seed_cloudwatch.py
COPY --chown=opspilot:opspilot scripts /app/scripts
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONPATH=/app ENVIRONMENT=production \
    MCP_HOST=0.0.0.0 EVALUATION_DATASET_DIR=/evaluation/datasets/v1
USER opspilot
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
