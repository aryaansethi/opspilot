# OpsPilot AI

AI-assisted incident investigation: hybrid retrieval (Postgres full-text + pgvector + RRF + optional cross-encoder rerank) over your runbooks and incident reports, grounded answers with validated citations, and (next phases) MCP-backed evidence from GitHub and CloudWatch.

Runs **entirely locally at zero cost**: Docker Compose (Postgres + pgvector, LocalStack) and Ollama for models. See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions.

## Status

| Phase | State |
|---|---|
| 1. Auth + workspaces | Done, tested |
| 2. Document ingestion (S3 → SQS → worker) | Done, tested |
| 3. Hybrid search + grounded Q&A | Done, tested |
| 4. MCP: CloudWatch server + backend MCP layer | Done, tested |
| 4b. MCP: GitHub server | Done, tested with a simulated GitHub API; live check pending token |
| 5. Investigation workflow | Planned |
| 6. Evaluation | Planned |
| 7. Terraform / CI | Planned |
| Frontend (Next.js) | In progress in `frontend/` |

## Prerequisites

- Docker (OrbStack or Docker Desktop)
- [uv](https://docs.astral.sh/uv/) and Python 3.12 (`uv python install 3.12`)
- [Ollama](https://ollama.com): `ollama pull bge-m3` and `ollama pull qwen3:8b`

## Run locally

```bash
docker compose up -d --wait            # postgres :5433, localstack :4566
cd backend
uv sync                                 # add --group rerank for reranking
cp .env.example .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000     # API → http://localhost:8000/docs
uv run python -m app.worker                          # ingestion worker (second terminal)

# CloudWatch MCP server (third terminal) + synthetic demo incident in LocalStack
CW_ALLOWED_LOG_GROUPS=/ecs/orders-api CW_ALLOWED_NAMESPACES=OpsPilot/OrdersApi \
  uv run python -m mcp_servers.cloudwatch.server                 # :8101/mcp
uv run --project . python ../scripts/seed_cloudwatch.py
```

GitHub MCP server (fourth terminal; reads GITHUB_TOKEN / GITHUB_ALLOWED_REPOS from backend/.env):

```bash
uv run --env-file .env python -m mcp_servers.github.server       # :8102/mcp
```

Then connect it to a workspace with `POST /api/v1/integrations`
(`{"kind": "cloudwatch", "config": {"log_groups": ["/ecs/orders-api"], "namespaces": ["OpsPilot/OrdersApi"]}}`)
and call read tools with `POST /api/v1/tools/invoke`.

Smoke test the whole flow with the demo corpus (from the repo root):

```bash
uv run --project backend python scripts/smoke_test.py --rerank
```

## Tests

```bash
cd backend
uv run pytest            # needs docker compose services; uses the opspilot_test database
uv run ruff check . && uv run mypy app
```

Tests use deterministic fake embeddings and a scripted fake LLM, so they do not need Ollama.

## Honest notes

- Lexical retrieval is **PostgreSQL full-text search (`ts_rank_cd`), not BM25**. A BM25 engine (OpenSearch) is a planned, measured comparison.
- Token counts used for chunk sizing are estimates (~4 characters per token).
- No benchmark numbers are claimed until the evaluation phase produces them.
- CloudWatch data in local development is **synthetic** (`scripts/seed_cloudwatch.py`) and is labelled as such.
- LocalStack's free edition only speaks CloudWatch's older `query` protocol; `mcp_servers/aws_compat.py` pins it when an endpoint override is set. Real AWS is unaffected.
- MCP servers live in `backend/mcp_servers/` (shared dependencies) and use the official MCP Python SDK v2 (`MCPServer`, streamable HTTP).
