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
| 4b. MCP: GitHub server | Done, tested; live check against a real repository passed |
| 5. Investigation workflow (state machine, SSE, approvals, audit) | Done, tested; live run on local model |
| 6. Evaluation (dataset v1, retrieval A–D, answer checks, dashboard) | Retrieval done and reported; answer-quality run in progress |
| 7. CI, containers, Terraform | In progress |
| Frontend (Next.js) | Done: all screens on the real API (mock mode for previews) |

## Prerequisites

- Docker (OrbStack or Docker Desktop)
- [uv](https://docs.astral.sh/uv/) and Python 3.12 (`uv python install 3.12`)
- [Ollama](https://ollama.com): `ollama pull bge-m3`, `ollama pull qwen3:8b`, then
  `ollama create opspilot-qwen3-8b -f docker/ollama/Modelfile` (same model with a 16K context window;
  Ollama's 4K default silently truncates investigation prompts)

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

## Evaluation results (dataset v1, held-out test split)

Retrieval over 70 held-out questions (56 answerable), measured by `evaluation/run.py` on 2026-11-14
([report](evaluation/reports/20261114-061751-retrieval-test.md), [method](evaluation/README.md)):

| Config | Recall@5 | MRR | nDCG@10 | p50 latency |
|---|---|---|---|---|
| A: Postgres full-text (not BM25) | 0.786 | 0.692 | 0.713 | 4 ms |
| B: vector (bge-m3) | 0.920 | 0.862 | 0.880 | 135 ms |
| C: hybrid, RRF k=60 | 0.893 | 0.779 | 0.805 | 142 ms |
| D: hybrid + cross-encoder rerank | 0.911 | 0.903 | 0.901 | 457 ms |

What this shows: reranking gives the best ranking quality; plain equal-weight RRF is *worse* than
vector-only here because the lexical side is weak on paraphrased and multi-section questions. RRF k
(10–100) made no measurable difference on the tuning split. The corpus is small and synthetic, so
treat these as a comparison between configurations, not as production accuracy.

## Honest notes

- Lexical retrieval is **PostgreSQL full-text search (`ts_rank_cd`), not BM25**. A BM25 engine (OpenSearch) is a planned, measured comparison.
- Token counts used for chunk sizing are estimates (~4 characters per token).
- No benchmark numbers are claimed until the evaluation phase produces them.
- CloudWatch data in local development is **synthetic** (`scripts/seed_cloudwatch.py`) and is labelled as such.
- LocalStack's free edition only speaks CloudWatch's older `query` protocol; `mcp_servers/aws_compat.py` pins it when an endpoint override is set. Real AWS is unaffected.
- MCP servers live in `backend/mcp_servers/` (shared dependencies) and use the official MCP Python SDK v2 (`MCPServer`, streamable HTTP).
