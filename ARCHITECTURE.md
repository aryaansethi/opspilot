# OpsPilot AI — Final Architecture & Build Plan

This document turns the system-design spec into concrete decisions. Where it departs from the spec, the departure and the reason are written down (see §11 Decision log).

---

## 1. One-paragraph summary

A **Next.js frontend on Vercel** (generated with v0, then hardened) talks to a **FastAPI modular monolith on AWS ECS Fargate**. The backend owns auth, workspaces, hybrid RAG (Postgres full-text + pgvector + RRF + optional reranker), and a **bounded investigation state machine** that calls **our own MCP servers** (GitHub, CloudWatch) over streamable HTTP. A **worker** process handles document ingestion (S3 → SQS) and runs investigations off the request path. Everything durable lives in **RDS PostgreSQL 16 + pgvector**. Progress streams to the browser over **Server-Sent Events** backed by Postgres `LISTEN/NOTIFY` — no Redis needed.

---

## 2. System diagram

```text
                    ┌───────────────────────────────────────────┐
  Browser ─────────▶│  Vercel — Next.js 15 (App Router)         │
                    │  shadcn/ui · Tailwind · TanStack Query    │
                    │  app.<domain>                              │
                    └───────────────────┬───────────────────────┘
                                        │ HTTPS (JSON + SSE)
                                        │ Bearer access token + httpOnly refresh cookie
                    ┌───────────────────▼───────────────────────┐
                    │  AWS ALB  — api.<domain> (ACM TLS)         │
                    └───────────────────┬───────────────────────┘
                                        │
     ┌──────────────────────────────────┼───────────────────────────────────┐
     │ ECS Fargate cluster              │                                   │
     │                                  ▼                                   │
     │   ┌──────────────────────────────────────────────┐                   │
     │   │ api  (FastAPI, uvicorn)                      │                   │
     │   │  auth · workspaces · documents · search/ask  │                   │
     │   │  investigations · approvals · audit · evals  │                   │
     │   │  SSE: /investigations/{id}/events            │                   │
     │   └───────┬───────────────────────┬──────────────┘                   │
     │           │ enqueue (SQS)         │ SQL / LISTEN                     │
     │   ┌───────▼───────────────────────┴──────────────┐                   │
     │   │ worker  (same codebase, different entrypoint)│                   │
     │   │  • ingestion jobs  (parse→chunk→embed→index) │                   │
     │   │  • investigation runs (state machine)        │──── MCP client ─┐ │
     │   └──────────────────────────────────────────────┘                 │ │
     │                                                                    │ │
     │   ┌─────────────────────┐   ┌──────────────────────────┐           │ │
     │   │ mcp-github          │◀──┤ streamable HTTP (private)├───────────┘ │
     │   │ FastMCP, read-only  │   └──────────────────────────┘             │
     │   └─────────────────────┘   ┌──────────────────────────┐             │
     │   ┌─────────────────────┐   │                          │             │
     │   │ mcp-cloudwatch      │◀──┘  (Jira added in P1)      │             │
     │   │ FastMCP, read-only  │                              │             │
     │   │ IAM task role (RO)  │                              │             │
     │   └─────────────────────┘                              │             │
     └────────────────────────────────────────────────────────────────────────┘
            │                │                 │                  │
     ┌──────▼──────┐  ┌──────▼─────┐   ┌───────▼───────┐  ┌───────▼────────┐
     │ RDS Postgres│  │ S3 (private│   │ SQS           │  │ Secrets Manager│
     │ 16+pgvector │  │ docs bucket│   │ ingest + DLQ  │  │ LLM/GitHub keys│
     └─────────────┘  └────────────┘   │ investigate   │  └────────────────┘
                                       └───────────────┘
                 LLM + embeddings: Amazon Bedrock or OpenAI (behind a provider interface)
                 Observability: CloudWatch Logs/Metrics/Alarms, structured JSON logs
```

---

## 3. Frontend — how we build it

### 3.1 Stack

| Concern | Choice | Why |
|---|---|---|
| Framework | **Next.js 15, App Router, TypeScript (strict)** | What v0 generates natively; deploys to Vercel with zero config |
| Rendering | Client components for app screens; server components only for the landing page | All data is per-user and behind auth — no SSR data fetching needed, keeps the backend the single source of truth |
| UI kit | **shadcn/ui + Tailwind CSS v4 + lucide-react** | v0 default; components are copied into the repo, so we own them |
| Data fetching | **TanStack Query v5** | Caching, retries, polling, optimistic updates for approvals |
| Forms | react-hook-form + zod | Same validation shapes as backend Pydantic models |
| Charts | Recharts (via shadcn `chart`) | Eval dashboard, metric sparklines |
| Streaming | `fetch` + ReadableStream SSE parser (custom hook) | Native `EventSource` can't send an `Authorization` header |
| Motion | `motion` (Framer Motion) — subtle only | Spec §6 |
| Tests | Vitest + Testing Library; Playwright for 3–4 critical flows | Spec §17 |

### 3.2 Frontend folder layout

```text
frontend/
├── app/
│   ├── (marketing)/page.tsx           # landing
│   ├── (auth)/login/page.tsx
│   ├── (auth)/register/page.tsx
│   └── (app)/                         # authenticated shell (sidebar + topbar)
│       ├── layout.tsx                 # AuthGuard + WorkspaceProvider
│       ├── dashboard/page.tsx
│       ├── knowledge/page.tsx         # document manager
│       ├── knowledge/[documentId]/page.tsx
│       ├── search/page.tsx            # search + ask + debug toggle
│       ├── investigations/page.tsx    # list
│       ├── investigations/new/page.tsx
│       ├── investigations/[id]/page.tsx        # live workspace
│       ├── investigations/[id]/report/page.tsx
│       ├── integrations/page.tsx
│       ├── evaluations/page.tsx
│       ├── evaluations/[runId]/page.tsx
│       └── audit/page.tsx
├── components/
│   ├── ui/                            # shadcn primitives
│   ├── layout/                        # sidebar, topbar, workspace switcher
│   ├── investigation/                 # stage-stepper, timeline, evidence-card, hypothesis-card, approval-panel
│   ├── knowledge/                     # upload-dropzone, document-table, status-badge
│   ├── search/                        # result-card, rank-debug-table
│   └── common/                        # empty-state, error-state, source-badge, citation-chip
├── lib/
│   ├── api/
│   │   ├── client.ts                  # fetch wrapper: base URL, auth header, refresh-on-401, error normalisation
│   │   ├── endpoints/*.ts             # one file per resource
│   │   └── mock/                      # mock adapter — ONLY active when NEXT_PUBLIC_API_MODE=mock
│   ├── auth/                          # token store (memory), AuthProvider
│   ├── sse.ts                         # useInvestigationEvents hook
│   └── types/api.ts                   # TS mirror of backend schemas (later: generated from OpenAPI)
└── tests/
```

### 3.3 Rules the frontend must follow

1. **No fake data in real flows.** Mock data lives only in `lib/api/mock/` and is enabled by `NEXT_PUBLIC_API_MODE=mock` (used for v0 previews and Storybook-style demos). Production build sets `real`.
2. **Every screen has loading, empty, and error states.**
3. **Tenant isolation is never done in the UI** — the UI just sends `X-Workspace-Id`; the backend enforces it.
4. **Provenance is always visible:** every evidence item shows a badge — `Knowledge base` vs `Live: GitHub` / `Live: CloudWatch` — plus a link/timestamp.
5. **Facts vs hypotheses are visually different** (different card style + label), and hypotheses never use the words "root cause" unless the backend marks `status = "confirmed"`.
6. **Write actions only through the Approval panel**, which shows the exact tool name and arguments before the user clicks Approve.
7. Types in `lib/types/api.ts` are replaced by `openapi-typescript` output once the backend exists.

---

## 4. Backend — how we build it

### 4.1 Stack

| Concern | Choice |
|---|---|
| Language/runtime | Python 3.12, `uv` for dependency management |
| API | FastAPI + Pydantic v2 |
| DB access | SQLAlchemy 2.0 (async, `asyncpg`) + Alembic |
| Database | PostgreSQL 16 + `pgvector` (HNSW index) |
| Lexical search (MVP) | Postgres full-text search (`tsvector` + `ts_rank_cd`) — **labelled as "Postgres FTS", not BM25** |
| Lexical search (P1 experiment) | OpenSearch BM25 behind the same `LexicalRetriever` interface |
| Embeddings | `EmbeddingProvider` interface. Default: Bedrock Titan Text Embeddings v2 or OpenAI `text-embedding-3-small`; local dev option: `bge-small-en-v1.5` via sentence-transformers |
| Reranker | `Reranker` interface. Default off. Options: `bge-reranker-base` (CPU, top-30 only) or a hosted rerank API |
| LLM | `LLMProvider` interface → Bedrock or OpenAI. Structured outputs (JSON schema) for planner + hypotheses |
| Auth | Argon2id password hashing (`argon2-cffi`), JWT access token (15 min) + rotating refresh token (httpOnly, Secure cookie, stored hashed in DB) |
| MCP | Official `mcp` Python SDK — `ClientSession` over streamable HTTP in the backend; `FastMCP` for our servers |
| Queue | SQS (`ingest`, `investigate`, each with a DLQ). LocalStack locally |
| Storage | S3 (presigned PUT uploads). LocalStack locally |
| Streaming | SSE endpoint; worker writes `investigation_events` rows and `NOTIFY investigation_<id>`; API `LISTEN`s and forwards |
| Rate limiting | `slowapi` per user + per IP on auth endpoints |
| Logging | `structlog` JSON → stdout → CloudWatch; request ID + workspace ID on every line; secret redaction processor |
| Tests | pytest, pytest-asyncio, testcontainers (real Postgres+pgvector), respx for HTTP mocks, fake MCP server fixture |
| Lint/type | ruff, mypy (strict on `app/rag`, `app/investigations`, `app/mcp`) |

### 4.2 Backend module layout (modular monolith)

```text
backend/
├── app/
│   ├── main.py                    # FastAPI app factory
│   ├── worker.py                  # SQS consumer entrypoint
│   ├── core/                      # config (pydantic-settings), security, logging, errors
│   ├── db/                        # engine, session, base, RLS helpers
│   ├── auth/                      # router, service, deps (get_current_user, get_workspace)
│   ├── workspaces/
│   ├── documents/                 # router, service, repository, upload (presign), models
│   ├── rag/
│   │   ├── ingestion/             # parsers (pdf via pypdf, md, txt), validators
│   │   ├── chunking/              # heading-aware chunker, keeps code/log blocks intact
│   │   ├── embeddings/            # provider interface + impls
│   │   ├── lexical/               # PostgresFTSRetriever (OpenSearchBM25Retriever later)
│   │   ├── vector/                # PgVectorRetriever
│   │   ├── fusion/                # rrf.py (pure function, heavily unit-tested)
│   │   ├── reranking/
│   │   ├── pipeline.py            # HybridSearch: filters → lexical ∥ vector → RRF → dedupe → rerank
│   │   └── generation/            # grounded answer prompt, citation validator
│   ├── mcp/
│   │   ├── registry.py            # loads tool_registry rows; allowlist + JSON-schema validation
│   │   ├── client.py              # session pool per server, timeouts, max result bytes
│   │   ├── policy.py              # read vs write, approval required, per-workspace enablement
│   │   └── audit.py               # writes tool_invocations (arguments redacted)
│   ├── investigations/
│   │   ├── state_machine.py       # explicit states + transitions (no free-form agent loop)
│   │   ├── planner.py             # LLM → constrained JSON plan → validated against allowed tasks
│   │   ├── tasks/                 # one module per task type (search_runbooks, query_cloudwatch_metrics…)
│   │   ├── evidence.py            # normalise RAG + tool output into evidence_items
│   │   ├── hypotheses.py
│   │   ├── report.py
│   │   └── events.py              # emit progress events (DB row + NOTIFY)
│   ├── approvals/
│   ├── audit/
│   ├── evaluations/
│   └── api/v1/router.py           # mounts all routers
├── migrations/
└── tests/
mcp_servers/
├── github/server.py               # FastMCP; PAT or GitHub App token from Secrets Manager; repo allowlist
└── cloudwatch/server.py           # FastMCP; boto3 with task role; log-group + namespace allowlist; max window 24h
evaluation/
├── datasets/v1/{corpus/,questions.jsonl}
├── retrieval/run.py               # A/B/C/D configs → Recall@k, MRR, nDCG, latency
├── answer_quality/
└── tool_use/
```

### 4.3 Request lifecycle examples

**Upload a document**
1. `POST /documents/upload-url` → backend validates type/size, creates `documents` row (`status=pending_upload`), returns presigned S3 PUT (key = `ws/<workspace_id>/docs/<document_id>/<filename>`).
2. Browser PUTs file directly to S3.
3. `POST /documents/complete-upload` → status `queued`, message on `ingest` SQS. (S3 event notifications are a P1 swap; explicit enqueue is easier to test.)
4. Worker: download → validate magic bytes → extract → chunk → hash (skip if unchanged) → embed in batches → upsert `document_chunks` (tsvector computed by a generated column) → `status=indexed`.

**Ask a question** (`POST /ask`)
`HybridSearch` → top-N chunks → grounded prompt (chunks wrapped in `<evidence id="…">` tags, system prompt says evidence is untrusted data) → structured answer `{answer, claims:[{text, evidence_ids}], insufficient_evidence: bool}` → **citation validator** drops any evidence ID not in the retrieved set → response.

**Run an investigation**
1. `POST /investigations` with question + optional service/env/time range.
2. API creates row (`RECEIVED`), enqueues on `investigate`, returns `202 {id}`.
3. Worker runs the state machine. If service or time range is missing → state `AWAITING_PARAMETERS`, emits event, stops. UI shows a form → `POST /investigations/{id}/continue` resumes.
4. Each task runs with its own timeout; failures mark that step `failed` and the run continues to `PARTIAL` rather than crashing.
5. Every state change and tool call emits an event → SSE → UI timeline.
6. Report generated; if the user asks for a Jira ticket, an `action_approvals` row is created (`pending`) and shown in the Approval panel. Nothing executes until `POST /approvals/{id}/approve`, which re-checks permission and executes exactly the stored arguments.

### 4.4 Investigation state machine

```text
RECEIVED → CLASSIFY_REQUEST → COLLECT_PARAMETERS ─(missing)→ AWAITING_PARAMETERS ─(continue)→┐
                                     │                                                         │
                                     ▼◀────────────────────────────────────────────────────────┘
                              PLAN_INVESTIGATION → RUN_KNOWLEDGE_RETRIEVAL → RUN_READ_TOOLS
                              → NORMALIZE_EVIDENCE → ANALYZE_HYPOTHESES → CHECK_CITATIONS
                              → GENERATE_REPORT → AWAITING_ACTION (optional) → COMPLETED

Terminal failure states: FAILED_INVALID_PARAMS · FAILED_LLM · FAILED_RETRIEVAL
Non-terminal degraded:   PARTIAL (some tools timed out / denied / returned nothing)
```

Hard limits per run: max 12 tool calls, max 3 LLM calls for planning/analysis, 120 s wall clock, 200 KB total tool output.

---

## 5. Data model (key columns)

All tables: `id UUID PK`, `created_at`, `updated_at`. Every tenant-owned table has `workspace_id UUID NOT NULL` + index, and a Postgres RLS policy on `current_setting('app.workspace_id')` as defence-in-depth.

| Table | Key columns |
|---|---|
| `users` | email (citext, unique), password_hash, display_name |
| `workspaces` | name, slug |
| `workspace_members` | workspace_id, user_id, role (`owner`/`member`/`viewer`) |
| `refresh_tokens` | user_id, token_hash, expires_at, revoked_at |
| `connected_integrations` | workspace_id, kind (`github`/`cloudwatch`/`jira`), config JSONB (allowlists), secret_arn, status |
| `documents` | workspace_id, title, source_type (`runbook`/`architecture`/`incident_report`/`other`), service, environment, s3_key, mime_type, size_bytes, content_hash, status, error, indexed_at, embedding_model |
| `document_chunks` | workspace_id, document_id, chunk_index, content, section_path, page_start, page_end, char_start, char_end, content_hash, `tsv tsvector GENERATED`, `embedding vector(<dim>)`, embedding_model |
| `document_ingestion_jobs` | document_id, attempt, status, error, started_at, finished_at |
| `investigations` | workspace_id, created_by, question, service, environment, time_start, time_end, incident_type, state, plan JSONB |
| `investigation_steps` | investigation_id, state, status, started_at, finished_at, detail JSONB |
| `investigation_events` | investigation_id, seq, type, payload JSONB (feeds SSE replay) |
| `evidence_items` | workspace_id, investigation_id, source_system (`knowledge_base`/`github`/`cloudwatch`/`jira`), source_reference (URL/doc+chunk id), title, excerpt, observed_at, time_range, metadata JSONB, retrieval_method, rank, reliability_notes |
| `hypotheses` | investigation_id, statement, supporting_evidence_ids UUID[], contradicting_evidence_ids UUID[], missing_evidence TEXT[], confidence_explanation, validation_steps TEXT[], status (`proposed`/`supported`/`refuted`/`confirmed`) |
| `investigation_reports` | investigation_id, version, content JSONB, markdown |
| `user_feedback` | workspace_id, user_id, target_type, target_id, rating (`up`/`down`), comment |
| `mcp_servers` | name, url, transport, enabled |
| `tool_registry` | server_id, name, description, input_schema JSONB, access (`read`/`write`), timeout_ms, max_result_bytes, requires_approval, enabled |
| `tool_invocations` | workspace_id, investigation_id, actor_user_id, tool_id, arguments_redacted JSONB, status, duration_ms, result_bytes, error |
| `action_approvals` | workspace_id, investigation_id, tool_id, arguments JSONB, status (`pending`/`approved`/`rejected`/`executed`/`failed`), requested_by, decided_by, decided_at, result JSONB |
| `audit_events` | workspace_id, actor_user_id, action, target_type, target_id, metadata JSONB, ip |
| `evaluation_datasets` / `_questions` / `_runs` / `_results` | dataset version, question, expected chunk IDs, expected facts, answerable; run config JSONB, metrics JSONB, per-question results |

Indexes: HNSW on `document_chunks.embedding`, GIN on `document_chunks.tsv`, btree on every `(workspace_id, …)` lookup.

---

## 6. API contract (v1)

Base: `https://api.<domain>/api/v1`. Auth: `Authorization: Bearer <access>`; workspace: `X-Workspace-Id: <uuid>`. Errors: `{ "error": { "code": "string", "message": "string", "details": {} } }`. Lists: `?cursor=&limit=` → `{ items: [], next_cursor: string|null }`.

| Method & path | Purpose |
|---|---|
| `POST /auth/register` · `POST /auth/login` | → `{ access_token, user }` + sets refresh cookie |
| `POST /auth/refresh` · `POST /auth/logout` · `GET /auth/me` | |
| `GET/POST /workspaces` · `GET /workspaces/{id}` | |
| `POST /documents/upload-url` | `{ filename, mime_type, size_bytes, source_type, service?, environment? }` → `{ document_id, upload_url, headers }` |
| `POST /documents/complete-upload` | `{ document_id }` |
| `GET /documents` · `GET /documents/{id}` · `DELETE /documents/{id}` · `POST /documents/{id}/reindex` | |
| `GET /documents/{id}/status` | `{ status, error?, chunk_count, indexed_at? }` |
| `POST /search` | `{ query, filters?, top_k, mode: "hybrid"|"lexical"|"vector", rerank: bool }` → `{ results: SearchResult[], latency_ms }` |
| `POST /search/debug` | same + per-result `{ lexical_rank, vector_rank, rrf_score, rerank_score }` (admin/dev only) |
| `POST /ask` | `{ question, filters? }` → `{ answer, claims[], citations: Evidence[], insufficient_evidence }` |
| `POST /investigations` · `GET /investigations` · `GET /investigations/{id}` | |
| `POST /investigations/{id}/continue` | supply missing params |
| `GET /investigations/{id}/events` | **SSE** stream; supports `Last-Event-ID` replay |
| `GET /investigations/{id}/evidence` · `/hypotheses` · `/report` · `/tool-calls` · `/approvals` | |
| `POST /investigations/{id}/actions` | request a write action (e.g. Jira issue) → creates pending approval |
| `POST /approvals/{id}/approve` · `POST /approvals/{id}/reject` | |
| `POST /feedback` | |
| `GET/POST /integrations` · `DELETE /integrations/{id}` · `POST /integrations/{id}/test` | |
| `GET /audit-events` | filters: actor, action, date range |
| `POST /evaluations/run` · `GET /evaluations/runs` · `GET /evaluations/runs/{id}` | |
| `GET /healthz` · `GET /readyz` | |

SSE event types: `state_changed`, `step_started`, `step_completed`, `step_failed`, `tool_call_started`, `tool_call_completed`, `evidence_added`, `hypothesis_added`, `report_ready`, `approval_requested`, `parameters_required`, `error`.

---

## 7. MCP integration plan

- **We write our own two servers** (`mcp_servers/github`, `mcp_servers/cloudwatch`) with `FastMCP`. Owning them lets us enforce allowlists, size caps and redaction at the source and makes them easy to mock in tests. (Community servers can be swapped in later behind the same registry.)
- **Transport:** streamable HTTP, each server its own ECS service, reachable only from the worker's security group. Locally: Docker Compose services.
- **Tools at MVP:**
  - GitHub: `list_recent_commits`, `get_commit_details`, `list_pull_requests`, `get_pull_request`, `search_code` (repo-allowlisted).
  - CloudWatch: `filter_log_events`, `get_metric_data`, `describe_alarms`, `get_alarm_history` (log-group/namespace allowlisted, max 24 h window, max 500 events).
  - Jira (P1): `search_issues`, `get_issue`, then `create_issue` as a **write** tool behind approval.
- **Registry is the gate:** on startup the backend calls `list_tools` on each server and only exposes tools that also exist *and are enabled* in `tool_registry`. The LLM planner chooses **task types**, not raw tool names; each task module maps to specific tools with code-built arguments (validated against JSON schema). The LLM never emits an arbitrary tool call.
- **Every call:** timeout → size cap → redaction → `tool_invocations` row → normalised `evidence_items`.

---

## 8. Retrieval & evaluation plan

- Chunking: heading-aware, target ~500 tokens, ~80 overlap, never split inside fenced code or a log block.
- Retrieval: lexical top-50 ∥ vector top-50 → RRF (k=60, configurable) → dedupe by `(document_id, overlapping char range)` → optional rerank top-30 → top-8 to the LLM.
- Eval dataset v1: ~40 synthetic docs (runbooks, architecture notes, 15 incident reports, deploy notes, log excerpts) and ~120 hand-reviewed questions (20% unanswerable), split 70/30 tune/held-out.
- Configs compared: A lexical, B vector, C hybrid RRF, D hybrid + rerank. Metrics: Recall@5/10, Precision@5, MRR, nDCG@5/10, p50/p95 latency. Answer quality: citation precision/coverage, abstention accuracy, faithfulness (LLM-judge **plus** a human-reviewed sample).
- Tool-use eval: fake MCP servers returning fixtures; test correct task selection, argument validity, timeout handling, denied-permission handling, approval enforcement.
- Results are stored in `evaluation_runs` and rendered in the dashboard; only real runs are shown.

---

## 9. AWS — minimum for the first deployable milestone

| Resource | Notes |
|---|---|
| VPC, 2 public + 2 private subnets | **No NAT Gateway.** ECS tasks run in public subnets with public IPs but security groups only accept traffic from the ALB (api) or from the worker SG (MCP servers). RDS in private subnets. |
| ALB + ACM certificate | `api.<domain>` |
| ECS Fargate cluster | `api` (0.5 vCPU/1 GB), `worker` (0.5/1 GB), `mcp-github` (0.25/0.5), `mcp-cloudwatch` (0.25/0.5) |
| ECR | 4 repos (one per image) |
| RDS PostgreSQL 16 | `db.t4g.micro`, 20 GB gp3, single-AZ, not public, automated backups 1 day |
| S3 | private documents bucket, block public access, SSE-S3, lifecycle rule |
| SQS | `ingest`, `investigate`, + DLQs |
| Secrets Manager | DB URL, JWT secret, LLM key (if OpenAI), GitHub token |
| IAM | task execution role; per-service task roles (api: S3 presign + SQS send; worker: S3 read + SQS consume + Bedrock invoke; mcp-cloudwatch: `logs:FilterLogEvents`, `cloudwatch:GetMetricData`, `cloudwatch:DescribeAlarms*` on allowlisted ARNs only) |
| CloudWatch | log groups with 7-day retention, alarms on 5xx rate, ECS CPU, RDS CPU, DLQ depth |
| AWS Budgets | monthly budget with 50/80/100% alerts — **create this first** |
| Frontend | **Vercel** (not CloudFront) — see §11 |

**Cost risks (verify in your region before provisioning):** ALB has a fixed hourly charge; RDS runs 24/7; each public IPv4 address is billed; four always-on Fargate tasks; LLM/embedding calls; CloudWatch log ingestion. OpenSearch (P1) has a significant minimum cost — add only for the BM25 experiment, then tear down. Mitigation: `terraform destroy` or scale ECS services to 0 and stop RDS between demo sessions.

Terraform modules: `network`, `ecr`, `s3`, `sqs`, `rds`, `ecs_service` (reused 4×), `iam`, `alb`, `cloudwatch`, `budgets`; environments in `infrastructure/terraform/envs/dev`.

CI/CD (GitHub Actions, OIDC — no long-lived keys): PR → ruff, mypy, pytest (testcontainers), frontend lint/typecheck/test/build, docker build, `terraform fmt -check && validate`. Main → build & push images → `aws ecs update-service` → wait stable → hit `/readyz`. Vercel deploys the frontend from the same repo (`frontend/` root directory) on push.

---

## 10. Milestones

| # | Milestone | Exit criteria |
|---|---|---|
| 1 | Foundation | Docker Compose (postgres+pgvector, localstack, api, worker); register/login/refresh; workspace CRUD; frontend auth + app shell against real API |
| 2 | Ingestion | Upload → S3 → SQS → worker → chunks with metadata; status polling in UI; delete + reindex |
| 3 | Hybrid RAG | FTS + pgvector + RRF + optional rerank; `/search`, `/search/debug`, `/ask` with validated citations and abstention |
| 4 | MCP | GitHub + CloudWatch servers; registry, policy, audit; integrations page with "test connection" |
| 5 | Investigations | State machine in worker; SSE; evidence/hypotheses/report; parameter collection; Jira approval flow (P1) |
| 6 | Evaluation | Dataset v1, runner, stored runs, dashboard |
| 7 | AWS + polish | Terraform, CI/CD, alarms, k6, README with real numbers |

---

## 11. Decision log (departures from the spec)

| Spec said | We chose | Reason |
|---|---|---|
| React + Vite | **Next.js (App Router) on Vercel** | You're generating the UI with v0, which outputs Next.js. We use it as a client-side app; no business logic in Next.js server routes. |
| CloudFront for frontend | **Vercel** | Free tier, preview deployments per PR, no Terraform needed for the frontend. |
| WebSocket for live progress | **SSE** | Progress is one-way (server → browser). SSE is plain HTTP, works through the ALB, auto-reconnects with `Last-Event-ID`, and is simpler to secure. |
| BM25 | **Postgres FTS for MVP, labelled honestly**; OpenSearch BM25 as a measured P1 experiment | Avoids OpenSearch cost until the comparison is ready (spec §6 allows this). |
| BGE-M3 embeddings | **Hosted embedding API by default**, local small model for dev | BGE-M3 on CPU Fargate is slow and memory-hungry; the provider interface keeps it swappable. |
| S3 event → SQS | **Explicit enqueue from `complete-upload`** first | Fewer moving parts, easier to test; switch to S3 events later if wanted. |
| Ollama context window | **Custom `opspilot-qwen3-8b` model with 16K context** (`docker/ollama/Modelfile`) | Ollama's 4K default silently truncated investigation prompts, which caused invented details and dropped evidence in testing. |
| Model output trust | **Citation and number checks** | Facts/hypotheses must cite retrieved evidence labels and may only contain numbers found in the cited evidence; anything else is removed and listed in the report (`removed_by_validation`). |
| Redis | **Not used** | Postgres `LISTEN/NOTIFY` covers live events at this scale. |
| OpenAI API or Amazon Bedrock | **Ollama, running locally** for LLM (an ~8B instruct model) + embeddings (`bge-m3`, 1024 dims); local `bge-reranker` via sentence-transformers | Project must be **zero cost**. Ollama exposes an OpenAI-compatible API, so the code uses the OpenAI SDK with `base_url=http://localhost:11434/v1` — switching to paid OpenAI later is a config change only. |
| AWS ECS/RDS deployment, real CloudWatch | **Local-first, zero cost**: Docker Compose for everything; LocalStack (free community edition) for S3, SQS and CloudWatch Logs/Metrics; the CloudWatch MCP server points at LocalStack with synthetic incident logs | Real AWS costs money. Terraform is still written and validated (`terraform validate`, no `apply`) so the deployment design is demonstrable; deploying is an optional later step only if free credits are available. |

### Cross-domain auth note
Use a custom domain with `app.<domain>` (Vercel) and `api.<domain>` (ALB) so the refresh cookie is same-site (`SameSite=Lax; Secure; HttpOnly; Domain=api.<domain>`). If you deploy on `*.vercel.app` without a custom domain, the refresh cookie becomes a third-party cookie and Safari will block it — in that case fall back to `SameSite=None` and accept that Safari users re-login when the access token expires.
