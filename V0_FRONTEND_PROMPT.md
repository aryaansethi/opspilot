# v0 Prompt — OpsPilot AI Frontend

**How to use:** paste the **Master prompt** into v0 as one message. If v0 cuts it short or skips screens, send the **Follow-up prompts** one at a time in the same chat. When you're happy, download the ZIP and share it back here for review against the checklist at the bottom.

---

## Master prompt (copy everything inside the box)

````text
Build the complete frontend for "OpsPilot AI", an AI DevOps incident-investigation platform. Engineers describe an incident; the backend searches internal docs (hybrid RAG) and live tools (GitHub, AWS CloudWatch via MCP), then produces an evidence-backed report with hypotheses. The backend is a separate FastAPI service — this project is FRONTEND ONLY.

## Tech requirements
- Next.js 15 App Router, TypeScript strict, Tailwind CSS, shadcn/ui, lucide-react icons, Geist Sans + Geist Mono fonts.
- TanStack Query v5 for all server data. react-hook-form + zod for forms. Recharts (shadcn chart) for charts. `motion` for subtle transitions only.
- All authenticated pages are client components. Do NOT create Next.js API routes or server actions for business logic — every call goes to the external backend at `process.env.NEXT_PUBLIC_API_BASE_URL` (e.g. http://localhost:8000/api/v1).
- Dark theme by default with a light theme toggle (next-themes). Responsive down to 375px; sidebar collapses to a sheet on mobile. Keyboard accessible, visible focus rings, aria labels on icon buttons.

## API layer (very important)
Create `lib/api/client.ts`: a typed fetch wrapper that
- prefixes NEXT_PUBLIC_API_BASE_URL,
- adds `Authorization: Bearer <accessToken>` (token kept in memory in an AuthProvider, never localStorage),
- adds `X-Workspace-Id` from the active workspace,
- sends `credentials: "include"` so the httpOnly refresh cookie works,
- on 401 calls POST /auth/refresh once, retries, otherwise logs out,
- normalises errors from `{ "error": { "code", "message", "details" } }` into an `ApiError` class.
Create one file per resource in `lib/api/endpoints/` (auth, workspaces, documents, search, investigations, approvals, integrations, audit, evaluations, feedback) exporting typed functions plus TanStack Query hooks.

Create a MOCK adapter in `lib/api/mock/` with realistic sample data, used ONLY when `process.env.NEXT_PUBLIC_API_MODE === "mock"`. Set NEXT_PUBLIC_API_MODE=mock in `.env.example` comments for preview, default "real". Components must never import mock data directly — only through the API layer. Never hardcode results inside components.

Create `lib/sse.ts` with a `useInvestigationEvents(investigationId)` hook that streams Server-Sent Events from GET /investigations/{id}/events using fetch + ReadableStream (NOT EventSource, because we need the Authorization header), parses `id:`/`event:`/`data:` lines, reconnects with `Last-Event-ID`, and invalidates the related TanStack Query caches on each event. In mock mode, simulate the event sequence with timers.

## Types — create lib/types/api.ts exactly matching these shapes
```ts
type UUID = string; type ISODate = string;
interface User { id: UUID; email: string; display_name: string }
interface Workspace { id: UUID; name: string; slug: string; role: "owner"|"member"|"viewer" }
interface Page<T> { items: T[]; next_cursor: string | null }

type SourceType = "runbook"|"architecture"|"incident_report"|"other";
type DocStatus = "pending_upload"|"queued"|"processing"|"indexed"|"failed";
interface Document { id: UUID; title: string; source_type: SourceType; service?: string; environment?: string;
  mime_type: string; size_bytes: number; status: DocStatus; error?: string; chunk_count: number;
  indexed_at?: ISODate; created_at: ISODate; embedding_model?: string }

interface SearchResult { chunk_id: UUID; document_id: UUID; document_title: string; source_type: SourceType;
  excerpt: string; section_path?: string; page_start?: number; page_end?: number; score: number;
  debug?: { lexical_rank: number|null; vector_rank: number|null; rrf_score: number; rerank_score: number|null } }

type SourceSystem = "knowledge_base"|"github"|"cloudwatch"|"jira";
interface Evidence { id: UUID; source_system: SourceSystem; title: string; source_reference: string; url?: string;
  excerpt: string; observed_at?: ISODate; time_range?: { start: ISODate; end: ISODate };
  retrieval_method?: string; rank?: number; reliability_notes?: string; metadata: Record<string, unknown> }

interface AskResponse { answer: string; claims: { text: string; evidence_ids: UUID[] }[];
  citations: Evidence[]; insufficient_evidence: boolean }

type InvestigationState = "RECEIVED"|"CLASSIFY_REQUEST"|"COLLECT_PARAMETERS"|"AWAITING_PARAMETERS"|
  "PLAN_INVESTIGATION"|"RUN_KNOWLEDGE_RETRIEVAL"|"RUN_READ_TOOLS"|"NORMALIZE_EVIDENCE"|"ANALYZE_HYPOTHESES"|
  "CHECK_CITATIONS"|"GENERATE_REPORT"|"AWAITING_ACTION"|"COMPLETED"|"PARTIAL"|
  "FAILED_INVALID_PARAMS"|"FAILED_LLM"|"FAILED_RETRIEVAL";
interface Investigation { id: UUID; question: string; service?: string; environment?: string;
  time_start?: ISODate; time_end?: ISODate; incident_type?: string; state: InvestigationState;
  missing_parameters?: ("service"|"environment"|"time_range")[]; created_by: User; created_at: ISODate; updated_at: ISODate }

interface Hypothesis { id: UUID; statement: string; status: "proposed"|"supported"|"refuted"|"confirmed";
  supporting_evidence_ids: UUID[]; contradicting_evidence_ids: UUID[]; missing_evidence: string[];
  confidence_explanation: string; validation_steps: string[] }

interface ToolCall { id: UUID; server: string; tool: string; access: "read"|"write";
  arguments_redacted: Record<string, unknown>; status: "running"|"succeeded"|"failed"|"timeout"|"denied";
  duration_ms?: number; result_bytes?: number; error?: string; started_at: ISODate }

interface ApprovalRequest { id: UUID; investigation_id: UUID; tool: string; server: string;
  arguments: Record<string, unknown>; status: "pending"|"approved"|"rejected"|"executed"|"failed";
  requested_by: User; decided_by?: User; decided_at?: ISODate; result?: { url?: string; key?: string } }

interface Report { investigation_id: UUID; version: number; overview: string; scope: string;
  observed_facts: { text: string; evidence_ids: UUID[] }[]; hypotheses: Hypothesis[];
  recommended_diagnostics: string[]; proposed_remediation: string[]; unknowns: string[];
  tool_summary: { total: number; succeeded: number; failed: number }; markdown: string; generated_at: ISODate }

interface InvestigationEvent { seq: number; type: "state_changed"|"step_started"|"step_completed"|"step_failed"|
  "tool_call_started"|"tool_call_completed"|"evidence_added"|"hypothesis_added"|"report_ready"|
  "approval_requested"|"parameters_required"|"error"; payload: Record<string, unknown>; at: ISODate }

interface Integration { id: UUID; kind: "github"|"cloudwatch"|"jira"; status: "connected"|"error"|"disabled";
  config: Record<string, unknown>; last_checked_at?: ISODate; tools: { name: string; access: "read"|"write"; enabled: boolean }[] }

interface AuditEvent { id: UUID; actor: User; action: string; target_type: string; target_id: UUID;
  metadata: Record<string, unknown>; created_at: ISODate }

interface EvaluationRun { id: UUID; dataset_name: string; dataset_version: string; config_label: string;
  config: Record<string, unknown>; status: "running"|"completed"|"failed"; started_at: ISODate; finished_at?: ISODate;
  metrics?: { recall_at_5?: number; recall_at_10?: number; precision_at_5?: number; mrr?: number; ndcg_at_5?: number;
  ndcg_at_10?: number; faithfulness?: number; citation_precision?: number; abstention_accuracy?: number;
  tool_success_rate?: number; latency_p50_ms?: number; latency_p95_ms?: number } }
```

## Endpoints (relative to NEXT_PUBLIC_API_BASE_URL)
POST /auth/register, POST /auth/login → {access_token, user}; POST /auth/refresh; POST /auth/logout; GET /auth/me
GET/POST /workspaces
POST /documents/upload-url {filename, mime_type, size_bytes, source_type, service?, environment?} → {document_id, upload_url, headers}; then PUT the file to upload_url; then POST /documents/complete-upload {document_id}
GET /documents, GET /documents/{id}, GET /documents/{id}/status, DELETE /documents/{id}, POST /documents/{id}/reindex
POST /search {query, filters?, top_k, mode:"hybrid"|"lexical"|"vector", rerank} → {results, latency_ms}; POST /search/debug (same shape, includes debug ranks)
POST /ask {question, filters?} → AskResponse
POST /investigations {question, service?, environment?, time_start?, time_end?} → 202 {id}
GET /investigations, GET /investigations/{id}, POST /investigations/{id}/continue {service?, environment?, time_start?, time_end?}
GET /investigations/{id}/events (SSE), /evidence, /hypotheses, /tool-calls, /approvals, /report
POST /investigations/{id}/actions {kind:"create_jira_issue", fields} → ApprovalRequest
POST /approvals/{id}/approve, POST /approvals/{id}/reject
POST /feedback {target_type, target_id, rating:"up"|"down", comment?}
GET/POST /integrations, DELETE /integrations/{id}, POST /integrations/{id}/test
GET /audit-events?actor=&action=&from=&to=&cursor=
POST /evaluations/run, GET /evaluations/runs, GET /evaluations/runs/{id}

## Routes & screens
Route groups: `(marketing)` landing, `(auth)` login/register, `(app)` authenticated shell with left sidebar (logo, workspace switcher, nav: Dashboard, Investigations, Search, Knowledge base, Integrations, Evaluations, Audit log; user menu at bottom) and a top bar (breadcrumbs, command palette trigger ⌘K, theme toggle). Wrap `(app)` in an AuthGuard that redirects to /login.

1. `/` Landing — hero ("Investigate incidents with evidence, not guesses"), 3-step how-it-works (Retrieve → Correlate → Report), feature grid (Hybrid search, Live tool evidence via MCP, Human-approved actions, Auditable reports, Measured retrieval quality), architecture strip, CTA. No fake customer logos, no fake stats.
2. `/login`, `/register` — zod-validated forms, inline errors, loading button state.
3. `/dashboard` — recent investigations (status badges), knowledge-base summary (documents by status), integrations health, pending approvals count, "New investigation" primary CTA. Empty states guide the user (e.g. "Upload your first runbook").
4. `/knowledge` — document table (title, type, service, env, status badge, chunks, indexed at, actions: view, reindex, delete with confirm dialog). Upload dialog with drag-and-drop, file type/size validation (PDF, MD, TXT; max 20 MB), source type + service + environment fields, per-file progress through the 3-step presigned flow, then poll status every 3s until indexed/failed. Filters by type/status/service.
   `/knowledge/[documentId]` — metadata panel + list of chunks (section path, page range, excerpt).
5. `/search` — big search input; tabs "Search" and "Ask". Mode segmented control (Hybrid / Lexical / Vector), Rerank switch, filters (source type, service, environment). Results as cards with document title, section, page, highlighted excerpt, score. A "Debug ranks" toggle shows a table: lexical rank, vector rank, RRF score, rerank score. Ask tab renders the answer with inline numbered citation chips [1] that open a side sheet with the cited evidence; if insufficient_evidence is true show a clear amber "Not enough evidence in your knowledge base" callout instead of an answer.
6. `/investigations` — table with question, service, env, state badge, created by, updated. Filter by state.
7. `/investigations/new` — form: incident question (textarea), service, environment (select), time range picker with presets (last 1h/6h/24h/custom). Warn (not block) if service or time range is empty: "OpsPilot will ask for these before querying live systems."
8. `/investigations/[id]` — THE KEY SCREEN. Three-column layout on desktop (stack on mobile):
   - Left: question card + horizontal/vertical stage stepper showing the state machine (completed ✓, current pulsing, failed ✕, skipped greyed). Below it a live activity timeline fed by SSE: each tool call shows server icon, tool name, collapsible redacted arguments (JSON in Geist Mono), status, duration.
   - Center: tabs "Evidence" | "Hypotheses" | "Report". Evidence cards show a SOURCE BADGE (Knowledge base = neutral/blue; Live · GitHub; Live · CloudWatch; Live · Jira), title, excerpt, timestamp or page, link out, and retrieval method/rank in small text. Filter by source. Hypothesis cards are visually distinct from facts (dashed border, "Hypothesis" label, status pill): statement, supporting evidence chips (green), contradicting chips (red), missing evidence list, confidence explanation in words (NO numeric confidence or percentage), validation steps checklist. Never show the phrase "root cause" unless status === "confirmed".
   - Right: "Actions" panel. When state is AWAITING_PARAMETERS show an inline form for the missing parameters → POST /continue. Approval panel: each pending ApprovalRequest shows server + tool name, an access badge "WRITE", and the EXACT arguments as a read-only key/value list, with Approve and Reject buttons; Approve opens a confirm dialog repeating the action. After execution show the returned issue key/URL. Also a "Create Jira ticket" button (only when report is ready) that opens a pre-filled editable form, then submits as an approval request — it does NOT execute directly.
   - States: PARTIAL shows an amber banner listing which steps failed; FAILED_* shows an error panel with retry guidance; thumbs up/down feedback on the report.
9. `/investigations/[id]/report` — clean printable report: overview, scope & time window, observed facts (each with citation chips), hypotheses with supporting/contradicting evidence, recommended diagnostics, proposed remediation, unknowns & limitations, tool execution summary. Buttons: Copy markdown, Print/PDF.
10. `/integrations` — cards for GitHub, AWS CloudWatch, Jira (Jira labelled "Coming soon" if not configured). Each shows status, last checked, allowlist config (repos / log groups / metric namespaces / AWS region), list of exposed tools with READ/WRITE badges and enable toggles (write tools show a lock icon + "Requires approval"), and a "Test connection" button. Never ask for or display raw secrets in plain text — token inputs are password-type and write-only.
11. `/evaluations` — run list (dataset name + version, config label, timestamp, status). Comparison view: grouped bar chart of Recall@5, Recall@10, MRR, nDCG@10 across configs (Lexical / Vector / Hybrid RRF / Hybrid + Rerank), latency p50/p95 chart, metric table. Every chart shows dataset version and run timestamp. If there are no runs, show an empty state "No evaluation runs yet" with a "Run evaluation" button — never placeholder numbers.
    `/evaluations/[runId]` — config JSON, metrics, per-question results table.
12. `/audit` — filterable, paginated table: time, actor, action, target, expandable metadata JSON.

## Design direction
Modern developer-tool aesthetic: calm, dense, precise. Neutral zinc/slate surfaces, one accent color (electric indigo #6366F1) used sparingly, semantic colors for status (emerald success, amber partial/warning, rose failed, sky running). 8px spacing grid, rounded-lg cards with 1px subtle borders, no heavy shadows, no gradients except a faint one on the landing hero. Monospace (Geist Mono) for IDs, log lines, JSON, commit SHAs, timestamps. Relative times with absolute time on hover tooltip. Skeleton loaders for every list. Toasts (sonner) for success/error. Do not copy Linear or Vercel exactly — original layout.

## Quality bar
- Every page has loading, empty, and error states.
- No `any` types. No hardcoded data in components. No console errors.
- Reusable components: SourceBadge, StatusBadge, StateStepper, EvidenceCard, HypothesisCard, CitationChip, ToolCallItem, ApprovalCard, JsonViewer, EmptyState, ErrorState, PageHeader.
- Include `.env.example` with NEXT_PUBLIC_API_BASE_URL and NEXT_PUBLIC_API_MODE, and a README section explaining mock vs real mode.
````

---

## Follow-up prompts (use only if needed)

**1 — if the investigation screen is thin**
```text
Rebuild /investigations/[id] fully: three-column layout, StateStepper driven by the InvestigationState enum, SSE-driven activity timeline using useInvestigationEvents (simulated in mock mode with ~1 event/second through all states ending at AWAITING_ACTION), Evidence/Hypotheses/Report tabs, AWAITING_PARAMETERS inline form, and the Approval panel with exact-argument display and a confirm dialog. Hypotheses must never show numeric confidence.
```

**2 — if the API layer was skipped or mocks leaked into components**
```text
Refactor so every component gets data only through hooks in lib/api/endpoints/*. Move all sample data into lib/api/mock/ behind NEXT_PUBLIC_API_MODE === "mock". Implement client.ts with Bearer token from memory, X-Workspace-Id, credentials:"include", single refresh-and-retry on 401, and ApiError normalisation. Remove any localStorage token storage.
```

**3 — if knowledge base / evaluations are incomplete**
```text
Complete /knowledge (3-step presigned upload with per-file progress and 3-second status polling) and /evaluations (grouped bar chart across Lexical/Vector/Hybrid RRF/Hybrid+Rerank configs, latency chart, dataset version + timestamp on each chart, real empty state with no placeholder numbers).
```

---

## Review checklist (what I'll check when you send the ZIP back)

- [ ] Next.js App Router, TS strict, no `any`, builds with `pnpm build` and `tsc --noEmit` clean
- [ ] No Next.js API routes / server actions doing business logic
- [ ] Single API client; tokens in memory only; refresh-on-401; `credentials: "include"`; `X-Workspace-Id`
- [ ] Mock data isolated behind `NEXT_PUBLIC_API_MODE`; no hardcoded results in components
- [ ] Types match `lib/types/api.ts` contract above (will later be replaced by OpenAPI-generated types)
- [ ] SSE via fetch stream (not EventSource), reconnect with `Last-Event-ID`
- [ ] Facts vs hypotheses visually distinct; no numeric confidence; "root cause" only when confirmed
- [ ] Source badges distinguish knowledge base vs live tools on every evidence item
- [ ] Write actions only via Approval panel showing exact arguments + confirm dialog
- [ ] Loading / empty / error states everywhere; eval dashboard has no placeholder numbers
- [ ] Accessibility: labels, focus states, keyboard nav, contrast in both themes
- [ ] Mobile layout at 375px
- [ ] Dependency hygiene: no unused packages, pinned versions, no secrets in repo
- [ ] Folder structure matches ARCHITECTURE.md §3.2
