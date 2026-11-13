/**
 * SAMPLE DATA FOR MOCK MODE ONLY (NEXT_PUBLIC_API_MODE=mock).
 * Nothing here is a real measurement, log line, commit or incident.
 * Components must never import this file — only lib/api/mock/index.ts does.
 */
import type {
  ApprovalRequest,
  AuditEvent,
  Document,
  DocumentChunk,
  EvaluationRun,
  Evidence,
  Hypothesis,
  Integration,
  Investigation,
  InvestigationEvent,
  Report,
  ToolCall,
  User,
  Workspace,
} from "@/lib/types/api"

const now = Date.now()
export const ago = (min: number) => new Date(now - min * 60_000).toISOString()

export const demoUser: User = { id: "u-demo", email: "demo@opspilot.dev", display_name: "Demo Engineer" }
const teammate: User = { id: "u-priya", email: "priya@example.com", display_name: "Priya Shah" }

export const workspaces: Workspace[] = [
  { id: "ws-platform", name: "Platform Team", slug: "platform", role: "owner" },
  { id: "ws-payments", name: "Payments Sandbox", slug: "payments", role: "member" },
]

export const documents: Document[] = [
  {
    id: "doc-1",
    title: "orders-api latency runbook.md",
    source_type: "runbook",
    service: "orders-api",
    environment: "production",
    mime_type: "text/markdown",
    size_bytes: 18_432,
    status: "indexed",
    chunk_count: 14,
    indexed_at: ago(60 * 26),
    created_at: ago(60 * 26),
    embedding_model: "sample-embedding-v1",
  },
  {
    id: "doc-2",
    title: "Orders platform architecture.pdf",
    source_type: "architecture",
    service: "orders-api",
    mime_type: "application/pdf",
    size_bytes: 1_204_224,
    status: "indexed",
    chunk_count: 42,
    indexed_at: ago(60 * 50),
    created_at: ago(60 * 50),
    embedding_model: "sample-embedding-v1",
  },
  {
    id: "doc-3",
    title: "INC-2041 postmortem — DB connection pool exhaustion.md",
    source_type: "incident_report",
    service: "orders-api",
    environment: "production",
    mime_type: "text/markdown",
    size_bytes: 9_870,
    status: "indexed",
    chunk_count: 8,
    indexed_at: ago(60 * 24 * 9),
    created_at: ago(60 * 24 * 9),
    embedding_model: "sample-embedding-v1",
  },
  {
    id: "doc-4",
    title: "RDS connection troubleshooting.md",
    source_type: "runbook",
    service: "shared-db",
    environment: "production",
    mime_type: "text/markdown",
    size_bytes: 7_210,
    status: "indexed",
    chunk_count: 6,
    indexed_at: ago(60 * 24 * 3),
    created_at: ago(60 * 24 * 3),
    embedding_model: "sample-embedding-v1",
  },
  {
    id: "doc-5",
    title: "payments-worker deploy notes.txt",
    source_type: "other",
    service: "payments-worker",
    environment: "staging",
    mime_type: "text/plain",
    size_bytes: 3_402,
    status: "processing",
    chunk_count: 0,
    created_at: ago(2),
  },
  {
    id: "doc-6",
    title: "legacy-scan.pdf",
    source_type: "other",
    mime_type: "application/pdf",
    size_bytes: 5_902_112,
    status: "failed",
    error: "No extractable text found (scanned image PDF).",
    chunk_count: 0,
    created_at: ago(60 * 5),
  },
]

const chunkText: Record<string, { section: string; text: string; page?: number }[]> = {
  "doc-1": [
    { section: "Symptoms", text: "p95 latency on orders-api above 800 ms for more than 5 minutes, often paired with HTTP 500s from the /checkout route." },
    { section: "First checks", text: "Check the DB connection pool metrics (ActiveConnections, PendingAcquire). A pending-acquire queue above 0 for sustained periods indicates pool contention." },
    { section: "First checks › Recent deploys", text: "Compare the running task definition revision with the previous one. Configuration changes to DB_POOL_MAX and DB_POOL_TIMEOUT_MS have caused regressions before." },
    { section: "Mitigation", text: "Roll back the task definition or restore the previous pool configuration. Confirm latency returns to baseline within 10 minutes." },
  ],
  "doc-2": [
    { section: "Request path", text: "Clients → ALB → orders-api (ECS) → inventory-svc (gRPC) and Postgres (RDS). orders-api holds a pooled connection per in-flight request.", page: 4 },
    { section: "Data tier", text: "RDS Postgres db.r6g.large, max_connections 400 shared by orders-api and billing-svc.", page: 7 },
  ],
  "doc-3": [
    { section: "Summary", text: "A config change reduced DB_POOL_MAX from 50 to 10. Under peak load requests queued for connections, raising p95 latency to 2.4 s and causing timeouts." },
    { section: "Detection", text: "Alarm orders-api-p95-latency fired 12 minutes after deploy. Logs showed 'timeout acquiring connection from pool'." },
    { section: "Action items", text: "Add a CI check that flags pool-size changes; add PendingAcquire to the service dashboard." },
  ],
  "doc-4": [
    { section: "Connection exhaustion", text: "If DatabaseConnections approaches max_connections, identify the top consumers with pg_stat_activity grouped by application_name." },
    { section: "Timeouts", text: "Client-side 'timeout acquiring connection' usually indicates pool limits in the application, not database saturation." },
  ],
}

export const chunks: Record<string, DocumentChunk[]> = Object.fromEntries(
  Object.entries(chunkText).map(([docId, list]) => [
    docId,
    list.map((c, i) => ({
      id: `${docId}-c${i}`,
      chunk_index: i,
      section_path: c.section,
      page_start: c.page,
      page_end: c.page,
      excerpt: c.text,
    })),
  ]),
)

// ---------------- Investigations ----------------

export const investigations: Investigation[] = [
  {
    id: "inv-1",
    question: "Investigate why orders-api response time increased after the latest deployment.",
    service: "orders-api",
    environment: "production",
    time_start: ago(180),
    time_end: ago(60),
    incident_type: "api_latency",
    state: "AWAITING_ACTION",
    created_by: demoUser,
    created_at: ago(55),
    updated_at: ago(50),
  },
  {
    id: "inv-2",
    question: "Checkout is throwing a lot of 500s, what's going on?",
    state: "AWAITING_PARAMETERS",
    missing_parameters: ["service", "time_range"],
    created_by: teammate,
    created_at: ago(20),
    updated_at: ago(19),
  },
  {
    id: "inv-3",
    question: "payments-worker memory keeps climbing until tasks get OOM-killed.",
    service: "payments-worker",
    environment: "staging",
    time_start: ago(60 * 12),
    time_end: ago(60 * 6),
    incident_type: "memory_pressure",
    state: "PARTIAL",
    failed_steps: ["GitHub: list_recent_commits timed out after 8s"],
    created_by: demoUser,
    created_at: ago(60 * 5),
    updated_at: ago(60 * 5 - 3),
  },
  {
    id: "inv-4",
    question: "Billing exports failed overnight.",
    service: "billing-svc",
    environment: "production",
    time_start: ago(60 * 24 * 2),
    time_end: ago(60 * 24 * 2 - 120),
    incident_type: "failed_job",
    state: "COMPLETED",
    created_by: teammate,
    created_at: ago(60 * 24 * 2),
    updated_at: ago(60 * 24 * 2 - 30),
  },
]

export function evidenceTemplate(service: string, start: string): Evidence[] {
  return [
    {
      id: "",
      source_system: "knowledge_base",
      title: "orders-api latency runbook › First checks",
      source_reference: "doc-1#chunk-1",
      excerpt: "A pending-acquire queue above 0 for sustained periods indicates pool contention.",
      retrieval_method: "hybrid_rrf",
      rank: 1,
      metadata: { document_id: "doc-1" },
    },
    {
      id: "",
      source_system: "knowledge_base",
      title: "INC-2041 postmortem › Summary",
      source_reference: "doc-3#chunk-0",
      excerpt: "A config change reduced DB_POOL_MAX from 50 to 10. Under peak load requests queued for connections…",
      retrieval_method: "hybrid_rrf",
      rank: 2,
      metadata: { document_id: "doc-3" },
    },
    {
      id: "",
      source_system: "cloudwatch",
      title: `${service} p95 latency (ALB TargetResponseTime)`,
      source_reference: `metric:AWS/ApplicationELB/TargetResponseTime?service=${service}`,
      excerpt: "p95 rose from ~180 ms to ~1.9 s starting 14 minutes after the deploy window opened.",
      observed_at: start,
      time_range: { start, end: new Date(Date.parse(start) + 3_600_000).toISOString() },
      retrieval_method: "get_metric_data",
      metadata: { statistic: "p95", period_s: 60 },
    },
    {
      id: "",
      source_system: "cloudwatch",
      title: `/ecs/${service} — 'timeout acquiring connection'`,
      source_reference: `logs:/ecs/${service}`,
      excerpt: "ERROR db.pool: timeout acquiring connection from pool after 2000ms (pending=37)",
      observed_at: new Date(Date.parse(start) + 900_000).toISOString(),
      retrieval_method: "filter_log_events",
      reliability_notes: "Sampled 500 of ~3,100 matching events.",
      metadata: { matches_sampled: 500 },
    },
    {
      id: "",
      source_system: "github",
      title: "a3f9c21 — chore: tune db pool for cost",
      source_reference: "acme/orders-api@a3f9c21",
      url: "https://github.com/acme/orders-api/commit/a3f9c21",
      excerpt: "config/production.env: DB_POOL_MAX 50 → 12, DB_POOL_TIMEOUT_MS 5000 → 2000",
      observed_at: new Date(Date.parse(start) - 600_000).toISOString(),
      retrieval_method: "list_recent_commits",
      metadata: { author: "sample-dev" },
    },
    {
      id: "",
      source_system: "github",
      title: "PR #482 — Reduce idle DB connections",
      source_reference: "acme/orders-api#482",
      url: "https://github.com/acme/orders-api/pull/482",
      excerpt: "Merged without load test; description notes 'should be fine at current traffic'.",
      observed_at: new Date(Date.parse(start) - 900_000).toISOString(),
      retrieval_method: "get_pull_request",
      metadata: {},
    },
  ]
}

export function hypothesisTemplate(ev: Evidence[]): Hypothesis[] {
  return [
    {
      id: "",
      statement: "Reducing DB_POOL_MAX in commit a3f9c21 may have caused requests to queue for database connections under normal peak load.",
      status: "supported",
      supporting_evidence_ids: [ev[0].id, ev[1].id, ev[3].id, ev[4].id],
      contradicting_evidence_ids: [],
      missing_evidence: ["Pool PendingAcquire metric for the same window", "Latency after reverting the pool setting"],
      confidence_explanation:
        "Timing lines up with the deploy and the log errors match the pool-timeout pattern from INC-2041, but no controlled rollback has been observed yet.",
      validation_steps: [
        "Compare DB_POOL_MAX between the current and previous task definition revisions",
        "Chart PendingAcquire alongside p95 latency",
        "Restore the previous pool size in staging under load and compare latency",
      ],
    },
    {
      id: "",
      statement: "A slowdown in the downstream inventory-svc could be adding latency to orders-api requests.",
      status: "proposed",
      supporting_evidence_ids: [ev[2].id],
      contradicting_evidence_ids: [ev[3].id],
      missing_evidence: ["inventory-svc latency metrics for the same window"],
      confidence_explanation:
        "Latency increase alone fits this, but the dominant errors are connection-pool timeouts, which point inside orders-api.",
      validation_steps: ["Query inventory-svc p95 latency for the same time window"],
    },
  ]
}

export function toolCallTemplate(service: string, start: string): Omit<ToolCall, "id">[] {
  return [
    { server: "cloudwatch", tool: "get_metric_data", access: "read", arguments_redacted: { namespace: "AWS/ApplicationELB", metric: "TargetResponseTime", stat: "p95", service, start }, status: "succeeded", duration_ms: 812, result_bytes: 4_210, started_at: start },
    { server: "cloudwatch", tool: "filter_log_events", access: "read", arguments_redacted: { log_group: `/ecs/${service}`, filter: "?ERROR ?timeout", limit: 500 }, status: "succeeded", duration_ms: 1_460, result_bytes: 61_002, started_at: start },
    { server: "github", tool: "list_recent_commits", access: "read", arguments_redacted: { repo: `acme/${service}`, since: start, limit: 20 }, status: "succeeded", duration_ms: 540, result_bytes: 8_930, started_at: start },
    { server: "github", tool: "get_pull_request", access: "read", arguments_redacted: { repo: `acme/${service}`, number: 482 }, status: "succeeded", duration_ms: 390, result_bytes: 3_120, started_at: start },
    { server: "cloudwatch", tool: "describe_alarms", access: "read", arguments_redacted: { prefix: service }, status: "succeeded", duration_ms: 300, result_bytes: 1_200, started_at: start },
  ]
}

export function reportTemplate(inv: Investigation, ev: Evidence[], hyp: Hypothesis[], tools: ToolCall[]): Report {
  const succeeded = tools.filter((t) => t.status === "succeeded").length
  const facts = [
    { text: `p95 latency for ${inv.service ?? "the service"} increased roughly tenfold during the selected window.`, evidence_ids: [ev[2].id] },
    { text: "Log events show repeated 'timeout acquiring connection from pool' errors in the same period.", evidence_ids: [ev[3].id] },
    { text: "A commit shortly before the window reduced DB_POOL_MAX and DB_POOL_TIMEOUT_MS.", evidence_ids: [ev[4].id, ev[5].id] },
    { text: "A previous incident (INC-2041) describes the same symptom after a pool-size reduction.", evidence_ids: [ev[1].id] },
  ]
  const md = [
    `# Incident report — ${inv.question}`,
    "",
    `**Scope:** ${inv.service ?? "unknown service"} (${inv.environment ?? "unknown env"}), ${inv.time_start ?? "?"} → ${inv.time_end ?? "?"}`,
    "",
    "## Observed facts",
    ...facts.map((f) => `- ${f.text}`),
    "",
    "## Hypotheses",
    ...hyp.map((h) => `- (${h.status}) ${h.statement}`),
  ].join("\n")
  return {
    investigation_id: inv.id,
    version: 1,
    overview: `Elevated latency on ${inv.service ?? "the service"} temporally associated with a configuration deploy. Evidence points to database connection-pool contention; causation is not yet established.`,
    scope: `${inv.service ?? "unknown"} · ${inv.environment ?? "unknown"} · selected window`,
    observed_facts: facts,
    hypotheses: hyp,
    recommended_diagnostics: [
      "Compare pool settings between the current and previous release",
      "Chart PendingAcquire and ActiveConnections against p95 latency",
      "Check inventory-svc latency to rule out a downstream cause",
    ],
    proposed_remediation: [
      "Restore DB_POOL_MAX to its previous value via a controlled config rollback",
      "Add a CI check that flags pool-size changes for review",
    ],
    unknowns: ["No pool metrics were available from connected tools", "Traffic volume relative to previous peaks was not checked"],
    tool_summary: { total: tools.length, succeeded, failed: tools.length - succeeded },
    markdown: md,
    generated_at: new Date().toISOString(),
  }
}

export const integrations: Integration[] = [
  {
    id: "int-github",
    kind: "github",
    status: "connected",
    config: { organization: "acme", repositories: ["acme/orders-api", "acme/payments-worker", "acme/billing-svc"] },
    last_checked_at: ago(12),
    tools: [
      { name: "list_recent_commits", access: "read", enabled: true },
      { name: "get_commit_details", access: "read", enabled: true },
      { name: "list_pull_requests", access: "read", enabled: true },
      { name: "get_pull_request", access: "read", enabled: true },
      { name: "search_code", access: "read", enabled: false },
    ],
  },
  {
    id: "int-cloudwatch",
    kind: "cloudwatch",
    status: "connected",
    config: { region: "us-east-1", log_groups: ["/ecs/orders-api", "/ecs/payments-worker"], metric_namespaces: ["AWS/ApplicationELB", "AWS/ECS", "AWS/RDS"], max_window_hours: 24 },
    last_checked_at: ago(12),
    tools: [
      { name: "filter_log_events", access: "read", enabled: true },
      { name: "get_metric_data", access: "read", enabled: true },
      { name: "describe_alarms", access: "read", enabled: true },
      { name: "get_alarm_history", access: "read", enabled: true },
    ],
  },
]

export const auditEvents: AuditEvent[] = [
  ["investigation.created", "investigation", "inv-1", demoUser, 55],
  ["tool.invoked", "tool", "get_metric_data", demoUser, 54],
  ["tool.invoked", "tool", "filter_log_events", demoUser, 54],
  ["tool.invoked", "tool", "list_recent_commits", demoUser, 53],
  ["approval.requested", "approval", "apr-1", demoUser, 48],
  ["document.uploaded", "document", "doc-5", teammate, 2],
  ["investigation.created", "investigation", "inv-2", teammate, 20],
  ["integration.tested", "integration", "int-github", demoUser, 12],
  ["document.deleted", "document", "doc-old", teammate, 60 * 30],
  ["auth.login", "user", "u-demo", demoUser, 70],
].map(([action, target_type, target_id, actor, min], i) => ({
  id: `aud-${i}`,
  actor: actor as User,
  action: action as string,
  target_type: target_type as string,
  target_id: target_id as string,
  metadata: { ip: "203.0.113.10", user_agent: "sample" },
  created_at: ago(min as number),
}))

export const evaluationRuns: EvaluationRun[] = [
  ["Lexical (Postgres FTS)", { mode: "lexical", rerank: false }, 0.58, 0.69, 0.47, 0.51, 0.55, 38, 71],
  ["Vector (pgvector)", { mode: "vector", rerank: false }, 0.63, 0.75, 0.52, 0.56, 0.6, 52, 96],
  ["Hybrid RRF k=60", { mode: "hybrid", rrf_k: 60, rerank: false }, 0.74, 0.84, 0.61, 0.66, 0.7, 81, 140],
  ["Hybrid RRF + rerank", { mode: "hybrid", rrf_k: 60, rerank: true, rerank_top_n: 30 }, 0.79, 0.86, 0.69, 0.72, 0.75, 410, 690],
].map(([label, config, r5, r10, p5, mrr, ndcg10, p50, p95], i) => ({
  id: `run-${i + 1}`,
  dataset_name: "opspilot-sample",
  dataset_version: "v1-mock",
  config_label: label as string,
  config: config as Record<string, unknown>,
  status: "completed" as const,
  started_at: ago(60 * 24 - i * 10),
  finished_at: ago(60 * 24 - i * 10 - 4),
  metrics: {
    recall_at_5: r5 as number,
    recall_at_10: r10 as number,
    precision_at_5: p5 as number,
    mrr: mrr as number,
    ndcg_at_10: ndcg10 as number,
    latency_p50_ms: p50 as number,
    latency_p95_ms: p95 as number,
  },
}))

export const pendingApprovalSeed = (invId: string): ApprovalRequest => ({
  id: "apr-1",
  investigation_id: invId,
  tool: "create_issue",
  server: "jira",
  arguments: {
    project: "OPS",
    issue_type: "Incident",
    summary: "orders-api p95 latency regression after pool config change",
    labels: ["latency", "orders-api"],
  },
  status: "pending",
  requested_by: demoUser,
})

export type EventLog = Record<string, InvestigationEvent[]>
