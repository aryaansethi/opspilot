# Demo script (about 6 minutes)

A walkthrough to record for a portfolio video or to run live in an interview. Every step uses the
real backend and local models; the only synthetic part is the CloudWatch incident data (labelled as
such in the app and in `scripts/seed_cloudwatch.py`).

## Before you record

1. Start the stack and seed it (see the README's *Quick start*). The seed writes the synthetic incident
   with the deploy **60 minutes before now**, so re-run it right before recording:

   ```bash
   docker compose --profile app run --rm seed        # or: uv run --project backend python scripts/seed_demo.py
   ```

2. Warm the local model once, so the first answer isn't slowed by loading it:

   ```bash
   curl -s localhost:11434/api/generate -d '{"model":"opspilot-qwen3-8b","prompt":"hi","stream":false}' >/dev/null
   ```

3. Browser at 1440×900, dark theme, signed out. Close other tabs and notifications.
4. Optional: start one investigation beforehand (step 4) so you can cut to a finished one if the
   live run is slow. A full investigation takes about 2 minutes on a laptop GPU.

Demo login: `demo@opspilot.dev` / `opspilot-demo-2026` (local only).

## Script

| # | Time | Do | Say |
|---|---|---|---|
| 1 | 0:00 | Landing page → **Sign in** with the demo login | "OpsPilot is an incident-investigation assistant. It searches internal runbooks, pulls live evidence from tools, and writes a report that cites every claim — and says what it doesn't know." |
| 2 | 0:30 | **Knowledge base** → open `orders-api-runbook` | "Documents go to S3, an SQS worker parses and chunks them by heading, and embeds each chunk with bge-m3 into pgvector. These are the chunks the search sees." |
| 3 | 1:00 | **Search** → `connection pool timeout after deploy`, turn on **Debug ranks** | "Hybrid search: Postgres full-text and vector search run in parallel and are fused with Reciprocal Rank Fusion. Debug shows each result's lexical rank, vector rank and fused score." |
| 4 | 1:30 | **Ask** tab → *What should I check first when orders-api latency spikes after a deploy?* | "Grounded answer: the model may only cite retrieved chunks; citations that don't map to a chunk are removed, and if evidence is thin it says so instead of guessing." |
| 5 | 2:15 | **New investigation** → *orders-api p95 latency and 5xx errors jumped right after the latest deploy. What changed?*, leave service and time range empty → **Start** | "It refuses to query live systems without a scope. It's a bounded state machine, not an open-ended agent." |
| 6 | 2:35 | Fill **service** `orders-api`, **Last 6 hours** → **Continue** | Point at the progress steps and the live activity feed: "Each step streams over Server-Sent Events. Here it's calling CloudWatch through an MCP server — read-only tools, allowlisted log groups, timeouts and size caps." |
| 7 | 3:30 | **Evidence** tab: filter **CloudWatch** vs **Knowledge base** | "Every item says where it came from — documentation or live data — with its source reference." |
| 8 | 3:50 | **Hypotheses** tab | "Hypotheses are kept separate from facts. A hypothesis is only marked *supported* when live evidence backs it; documentation alone keeps it *proposed*." |
| 9 | 4:15 | **Report** tab → **Full report** | "Observed facts cite evidence labels; statements whose numbers weren't in the evidence were removed and are listed under Unknowns." |
| 10 | 4:45 | **Create Jira ticket** → **Request approval** → **Approve** | "Write actions never run on their own: the exact arguments are shown and need approval. There's no Jira server connected here, so it fails honestly instead of pretending." |
| 11 | 5:15 | **Audit log** | "Every tool call, approval and change is recorded." |
| 12 | 5:30 | **Evaluations** → Test set; open the Hybrid RRF run, expand a miss | "Retrieval is measured on a versioned, held-out question set: Recall@5, MRR, nDCG per strategy. Reranking ranks best; plain RRF loses to vector-only here because full-text is weak on paraphrases — the numbers drove that conclusion." |

## If something goes wrong

- **Investigation finds no CloudWatch evidence** → the synthetic incident is older than the time window; re-run the seed.
- **Answers take over a minute** → the model wasn't warm; cut to the pre-run investigation.
- **"Not Found" on a page** → the API container isn't up: `docker compose --profile app ps`.

## Interview talking points

- **Why a state machine, not an agent loop:** predictable cost and latency, every step observable and testable, and a clear place to stop for missing parameters or approvals.
- **Why MCP for tools:** tool servers run as separate processes with their own credentials (only `mcp-github` ever sees the GitHub token); the backend enforces an allowlist, argument policies, timeouts and output caps on top.
- **Hallucination controls:** citation validation, number checks against evidence, "insufficient evidence" abstention (100% on unanswerable test questions), and a stricter rule for marking hypotheses supported.
- **Honest evaluation:** held-out test split, dataset hash in every run, per-question drill-down, and what isn't measured (faithfulness) is stated rather than shown as zero.
- **Security:** access token only in memory, refresh token in an httpOnly cookie, per-workspace isolation on every query, presigned uploads, least-privilege IAM in the (unapplied) Terraform.
