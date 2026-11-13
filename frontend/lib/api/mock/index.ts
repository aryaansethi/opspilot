/**
 * Mock adapter — implements ApiContract with in-memory sample data so the UI can be
 * previewed without a backend. Only used when NEXT_PUBLIC_API_MODE=mock.
 */
import { ApiError } from "../client"
import type { ApiContract } from "../contract"
import * as seed from "./data"
import type {
  ApprovalRequest,
  AuditEvent,
  Document,
  EvaluationRun,
  Evidence,
  Hypothesis,
  Investigation,
  InvestigationEvent,
  InvestigationEventType,
  InvestigationState,
  Report,
  SearchRequest,
  SearchResult,
  ToolCall,
} from "@/lib/types/api"

const SESSION_KEY = "opspilot_mock_session" // stands in for the httpOnly refresh cookie
const uid = () => (typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2))
const delay = (ms = 250 + Math.random() * 250) => new Promise((r) => setTimeout(r, ms))
const clone = <T,>(v: T): T => structuredClone(v)

function notFound(what: string): never {
  throw new ApiError(404, "not_found", `${what} not found`)
}

// ---------------- In-memory store ----------------

interface InvStore {
  evidence: Evidence[]
  hypotheses: Hypothesis[]
  toolCalls: ToolCall[]
  approvals: ApprovalRequest[]
  report: Report | null
  events: InvestigationEvent[]
}

const db = {
  documents: clone(seed.documents),
  chunks: clone(seed.chunks),
  investigations: clone(seed.investigations),
  inv: {} as Record<string, InvStore>,
  integrations: clone(seed.integrations),
  audit: clone(seed.auditEvents),
  runs: clone(seed.evaluationRuns),
}

const subscribers: Record<string, Set<(e: InvestigationEvent) => void>> = {}

function store(id: string): InvStore {
  if (!db.inv[id]) db.inv[id] = { evidence: [], hypotheses: [], toolCalls: [], approvals: [], report: null, events: [] }
  return db.inv[id]
}

function findInv(id: string): Investigation {
  return db.investigations.find((i) => i.id === id) ?? notFound("Investigation")
}

function emit(id: string, type: InvestigationEventType, payload: Record<string, unknown> = {}) {
  const s = store(id)
  const e: InvestigationEvent = { seq: s.events.length + 1, type, payload, at: new Date().toISOString() }
  s.events.push(e)
  subscribers[id]?.forEach((fn) => fn(e))
}

function setState(id: string, state: InvestigationState) {
  const inv = findInv(id)
  inv.state = state
  inv.updated_at = new Date().toISOString()
  emit(id, "state_changed", { state })
}

function audit(action: string, target_type: string, target_id: string) {
  const e: AuditEvent = {
    id: uid(),
    actor: seed.demoUser,
    action,
    target_type,
    target_id,
    metadata: { source: "mock" },
    created_at: new Date().toISOString(),
  }
  db.audit.unshift(e)
}

/** Fill an investigation's evidence/tools/hypotheses/report synchronously (for seeded rows). */
function hydrateComplete(inv: Investigation, opts: { toolFailures?: number } = {}) {
  const s = store(inv.id)
  const start = inv.time_start ?? seed.ago(120)
  const ev = seed.evidenceTemplate(inv.service ?? "service", start).map((e) => ({ ...e, id: uid() }))
  const tools = seed.toolCallTemplate(inv.service ?? "service", start).map((t) => ({ ...t, id: uid() })) as ToolCall[]
  const hyp = seed.hypothesisTemplate(ev).map((h) => ({ ...h, id: uid() }))
  if (opts.toolFailures) {
    // GitHub timed out: drop the commit/PR evidence and the hypothesis that relied on it.
    tools[2] = { ...tools[2], status: "timeout", duration_ms: 8000, result_bytes: 0, error: "Timed out after 8000 ms" }
    tools.splice(3, 1)
    ev.splice(4, 2)
    hyp.splice(0, 1)
  }
  s.evidence = ev
  s.toolCalls = tools
  s.hypotheses = hyp
  s.report = opts.toolFailures ? null : seed.reportTemplate(inv, ev, hyp, tools)
  const states: InvestigationState[] = [
    "RECEIVED", "CLASSIFY_REQUEST", "COLLECT_PARAMETERS", "PLAN_INVESTIGATION", "RUN_KNOWLEDGE_RETRIEVAL",
    "RUN_READ_TOOLS", "NORMALIZE_EVIDENCE", "ANALYZE_HYPOTHESES", "CHECK_CITATIONS", "GENERATE_REPORT",
  ]
  const at = inv.created_at
  s.events = states.map((st, i) => ({ seq: i + 1, type: "state_changed" as const, payload: { state: st }, at }))
  tools.forEach((t) =>
    s.events.push({ seq: s.events.length + 1, type: "tool_call_completed", payload: { tool_call_id: t.id, tool: t.tool, status: t.status }, at }),
  )
  s.events.push({ seq: s.events.length + 1, type: "state_changed", payload: { state: inv.state }, at: inv.updated_at })
}

// Seed rich data for the sample investigations.
for (const inv of db.investigations) {
  if (inv.id === "inv-1" || inv.id === "inv-4") hydrateComplete(inv)
  if (inv.id === "inv-3") hydrateComplete(inv, { toolFailures: 1 })
  if (inv.id === "inv-2") {
    const s = store(inv.id)
    ;(["RECEIVED", "CLASSIFY_REQUEST", "COLLECT_PARAMETERS"] as const).forEach((st, i) =>
      s.events.push({ seq: i + 1, type: "state_changed", payload: { state: st }, at: inv.created_at }),
    )
    s.events.push({ seq: 4, type: "parameters_required", payload: { missing: inv.missing_parameters }, at: inv.created_at })
    s.events.push({ seq: 5, type: "state_changed", payload: { state: "AWAITING_PARAMETERS" }, at: inv.updated_at })
  }
}
store("inv-1").approvals.push(seed.pendingApprovalSeed("inv-1"))

// ---------------- Simulated investigation engine ----------------

const STEP_MS = 900

function schedule(steps: (() => void)[]) {
  steps.forEach((fn, i) => setTimeout(fn, STEP_MS * (i + 1)))
}

function startRun(id: string) {
  const inv = findInv(id)
  const missing: Investigation["missing_parameters"] = []
  if (!inv.service) missing.push("service")
  if (!inv.time_start || !inv.time_end) missing.push("time_range")
  schedule([
    () => setState(id, "CLASSIFY_REQUEST"),
    () => {
      inv.incident_type = /memory|oom/i.test(inv.question) ? "memory_pressure" : /500|error/i.test(inv.question) ? "http_errors" : "api_latency"
      setState(id, "COLLECT_PARAMETERS")
    },
    () => {
      if (missing.length) {
        inv.missing_parameters = missing
        emit(id, "parameters_required", { missing })
        setState(id, "AWAITING_PARAMETERS")
      } else {
        resumeRun(id)
      }
    },
  ])
}

function resumeRun(id: string) {
  const inv = findInv(id)
  const s = store(id)
  const start = inv.time_start ?? new Date().toISOString()
  const ev = seed.evidenceTemplate(inv.service ?? "service", start).map((e) => ({ ...e, id: uid() }))
  const tools = seed.toolCallTemplate(inv.service ?? "service", start).map((t) => ({ ...t, id: uid() })) as ToolCall[]
  const toolEvidence: (number | null)[] = [2, 3, 4, 5, null]

  const addEvidence = (e: Evidence) => {
    s.evidence.push(e)
    emit(id, "evidence_added", { evidence_id: e.id, source_system: e.source_system })
  }

  const steps: (() => void)[] = [
    () => setState(id, "PLAN_INVESTIGATION"),
    () => {
      setState(id, "RUN_KNOWLEDGE_RETRIEVAL")
      emit(id, "step_started", { step: "search_runbooks" })
    },
    () => {
      addEvidence(ev[0])
      addEvidence(ev[1])
      emit(id, "step_completed", { step: "search_runbooks", results: 2 })
    },
    () => setState(id, "RUN_READ_TOOLS"),
  ]
  tools.forEach((t, i) => {
    steps.push(() => {
      const running: ToolCall = { ...t, status: "running", duration_ms: undefined, result_bytes: undefined, started_at: new Date().toISOString() }
      s.toolCalls.push(running)
      emit(id, "tool_call_started", { tool_call_id: t.id, tool: t.tool, server: t.server })
    })
    steps.push(() => {
      const idx = s.toolCalls.findIndex((x) => x.id === t.id)
      s.toolCalls[idx] = { ...t, started_at: s.toolCalls[idx].started_at }
      emit(id, "tool_call_completed", { tool_call_id: t.id, tool: t.tool, status: t.status })
      const evIdx = toolEvidence[i]
      if (evIdx !== null) addEvidence(ev[evIdx])
    })
  })
  steps.push(
    () => setState(id, "NORMALIZE_EVIDENCE"),
    () => setState(id, "ANALYZE_HYPOTHESES"),
    () => {
      const hyp = seed.hypothesisTemplate(ev).map((h) => ({ ...h, id: uid() }))
      hyp.forEach((h) => {
        s.hypotheses.push(h)
        emit(id, "hypothesis_added", { hypothesis_id: h.id })
      })
    },
    () => setState(id, "CHECK_CITATIONS"),
    () => setState(id, "GENERATE_REPORT"),
    () => {
      s.report = seed.reportTemplate(inv, s.evidence, s.hypotheses, s.toolCalls)
      emit(id, "report_ready", { version: 1 })
      setState(id, "AWAITING_ACTION")
    },
  )
  schedule(steps)
}

// ---------------- Search helpers ----------------

function tokens(q: string) {
  return q.toLowerCase().split(/[^a-z0-9_]+/).filter((t) => t.length > 2)
}

function runSearch(input: SearchRequest, withDebug: boolean): SearchResult[] {
  const qt = tokens(input.query)
  const all = db.documents
    .filter((d) => d.status === "indexed")
    .filter((d) => !input.filters?.source_type || d.source_type === input.filters.source_type)
    .filter((d) => !input.filters?.service || d.service === input.filters.service)
    .filter((d) => !input.filters?.environment || d.environment === input.filters.environment)
    .flatMap((d) => (db.chunks[d.id] ?? []).map((c) => ({ d, c })))

  const lexScored = all
    .map((x) => ({ ...x, lex: qt.filter((t) => x.c.excerpt.toLowerCase().includes(t)).length }))
    .filter((x) => x.lex > 0)
    .sort((a, b) => b.lex - a.lex)
  const vecScored = all
    // Crude stand-in for semantic similarity: title/section matches plus prefix matches.
    .map((x) => ({
      ...x,
      vec:
        qt.filter((t) => (x.c.section_path ?? "").toLowerCase().includes(t) || x.d.title.toLowerCase().includes(t)).length +
        qt.filter((t) => x.c.excerpt.toLowerCase().includes(t.slice(0, 4))).length * 0.5,
    }))
    .filter((x) => x.vec > 0)
    .sort((a, b) => b.vec - a.vec)

  const lexRank = new Map(lexScored.map((x, i) => [x.c.id, i + 1]))
  const vecRank = new Map(vecScored.map((x, i) => [x.c.id, i + 1]))
  const k = 60
  const ids = new Set<string>()
  if (input.mode !== "vector") lexScored.forEach((x) => ids.add(x.c.id))
  if (input.mode !== "lexical") vecScored.forEach((x) => ids.add(x.c.id))

  const results = [...ids].map((cid) => {
    const x = all.find((a) => a.c.id === cid)!
    const lr = input.mode === "vector" ? null : lexRank.get(cid) ?? null
    const vr = input.mode === "lexical" ? null : vecRank.get(cid) ?? null
    const rrf = (lr ? 1 / (k + lr) : 0) + (vr ? 1 / (k + vr) : 0)
    const rerank = input.rerank ? Math.min(0.99, rrf * 30 + (lr === 1 ? 0.2 : 0)) : null
    const r: SearchResult = {
      chunk_id: cid,
      document_id: x.d.id,
      document_title: x.d.title,
      source_type: x.d.source_type,
      excerpt: x.c.excerpt,
      section_path: x.c.section_path,
      page_start: x.c.page_start,
      page_end: x.c.page_end,
      score: rerank ?? rrf,
    }
    if (withDebug) r.debug = { lexical_rank: lr, vector_rank: vr, rrf_score: rrf, rerank_score: rerank }
    return r
  })
  return results.sort((a, b) => b.score - a.score).slice(0, input.top_k)
}

// ---------------- Contract implementation ----------------

export const mockApi: ApiContract = {
  auth: {
    async register(input) {
      await delay()
      sessionStorage.setItem(SESSION_KEY, "1")
      return { access_token: "mock-access-token", user: { ...seed.demoUser, email: input.email, display_name: input.display_name } }
    },
    async login(input) {
      await delay()
      if (input.password.length < 8) throw new ApiError(401, "invalid_credentials", "Invalid email or password")
      sessionStorage.setItem(SESSION_KEY, "1")
      return { access_token: "mock-access-token", user: { ...seed.demoUser, email: input.email } }
    },
    async refresh() {
      await delay(100)
      return sessionStorage.getItem(SESSION_KEY) === "1"
    },
    async logout() {
      sessionStorage.removeItem(SESSION_KEY)
    },
    async me() {
      await delay(100)
      return seed.demoUser
    },
  },
  workspaces: {
    async list() {
      await delay()
      return clone(seed.workspaces)
    },
    async create(input) {
      await delay()
      const ws = { id: uid(), name: input.name, slug: input.name.toLowerCase().replace(/\W+/g, "-"), role: "owner" as const }
      seed.workspaces.push(ws)
      return ws
    },
  },
  documents: {
    async list(params) {
      await delay()
      const items = db.documents
        .filter((d) => !params?.source_type || d.source_type === params.source_type)
        .filter((d) => !params?.status || d.status === params.status)
        .filter((d) => !params?.service || d.service === params.service)
      return { items: clone(items), next_cursor: null }
    },
    async get(id) {
      await delay()
      return clone(db.documents.find((d) => d.id === id) ?? notFound("Document"))
    },
    async chunks(id) {
      await delay()
      return clone(db.chunks[id] ?? [])
    },
    async status(id) {
      await delay(100)
      const d = db.documents.find((x) => x.id === id) ?? notFound("Document")
      return { status: d.status, error: d.error, chunk_count: d.chunk_count, indexed_at: d.indexed_at }
    },
    async uploadUrl(input) {
      await delay()
      const doc: Document = {
        id: uid(),
        title: input.filename,
        source_type: input.source_type,
        service: input.service,
        environment: input.environment,
        mime_type: input.mime_type,
        size_bytes: input.size_bytes,
        status: "pending_upload",
        chunk_count: 0,
        created_at: new Date().toISOString(),
      }
      db.documents.unshift(doc)
      return { document_id: doc.id, upload_url: "mock://upload", headers: {} }
    },
    async uploadFile(_target, _file, onProgress) {
      for (let p = 10; p <= 100; p += 15) {
        await delay(120)
        onProgress(Math.min(100, p))
      }
      onProgress(100)
    },
    async completeUpload(id) {
      await delay()
      const d = db.documents.find((x) => x.id === id) ?? notFound("Document")
      d.status = "queued"
      setTimeout(() => (d.status = "processing"), 1500)
      setTimeout(() => {
        d.status = "indexed"
        d.chunk_count = 3 + Math.floor(Math.random() * 10)
        d.indexed_at = new Date().toISOString()
        d.embedding_model = "sample-embedding-v1"
        db.chunks[d.id] = [{ id: `${d.id}-c0`, chunk_index: 0, section_path: "Document", excerpt: `Sample chunk for ${d.title} (mock mode).` }]
      }, 5000)
      audit("document.uploaded", "document", id)
      return clone(d)
    },
    async remove(id) {
      await delay()
      db.documents = db.documents.filter((d) => d.id !== id)
      audit("document.deleted", "document", id)
    },
    async reindex(id) {
      await delay()
      const d = db.documents.find((x) => x.id === id) ?? notFound("Document")
      d.status = "queued"
      d.error = undefined
      setTimeout(() => (d.status = "processing"), 1200)
      setTimeout(() => {
        d.status = d.id === "doc-6" ? "failed" : "indexed"
        if (d.id === "doc-6") d.error = "No extractable text found (scanned image PDF)."
        else d.indexed_at = new Date().toISOString()
      }, 4000)
      return clone(d)
    },
  },
  search: {
    async search(input) {
      const t = performance.now()
      await delay(300)
      return { results: runSearch(input, false), latency_ms: Math.round(performance.now() - t) }
    },
    async debug(input) {
      const t = performance.now()
      await delay(350)
      return { results: runSearch(input, true), latency_ms: Math.round(performance.now() - t) }
    },
    async ask(input) {
      await delay(900)
      const results = runSearch({ query: input.question, filters: input.filters, top_k: 3, mode: "hybrid", rerank: false }, false)
      if (results.length === 0) {
        return { answer: "", claims: [], citations: [], insufficient_evidence: true }
      }
      const citations: Evidence[] = results.map((r, i) => ({
        id: `cit-${i}`,
        source_system: "knowledge_base",
        title: `${r.document_title}${r.section_path ? ` › ${r.section_path}` : ""}`,
        source_reference: `${r.document_id}#${r.chunk_id}`,
        excerpt: r.excerpt,
        retrieval_method: "hybrid_rrf",
        rank: i + 1,
        metadata: { document_id: r.document_id },
      }))
      const claims = citations.map((c) => ({ text: c.excerpt, evidence_ids: [c.id] }))
      return {
        answer: claims.map((c, i) => `${c.text} [${i + 1}]`).join(" "),
        claims,
        citations,
        insufficient_evidence: false,
      }
    },
  },
  investigations: {
    async list(params) {
      await delay()
      const items = db.investigations
        .filter((i) => !params?.state || i.state === params.state)
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      return { items: clone(items), next_cursor: null }
    },
    async get(id) {
      await delay(150)
      return clone(findInv(id))
    },
    async create(input) {
      await delay()
      const inv: Investigation = {
        id: uid(),
        ...input,
        state: "RECEIVED",
        created_by: seed.demoUser,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      db.investigations.unshift(inv)
      emit(inv.id, "state_changed", { state: "RECEIVED" })
      audit("investigation.created", "investigation", inv.id)
      startRun(inv.id)
      return { id: inv.id }
    },
    async continue(id, input) {
      await delay()
      const inv = findInv(id)
      if (inv.state !== "AWAITING_PARAMETERS") throw new ApiError(409, "invalid_state", "Investigation is not waiting for parameters")
      Object.assign(inv, input)
      inv.missing_parameters = undefined
      setState(id, "COLLECT_PARAMETERS")
      resumeRun(id)
      return clone(inv)
    },
    async evidence(id) {
      await delay(150)
      return clone(store(id).evidence)
    },
    async hypotheses(id) {
      await delay(150)
      return clone(store(id).hypotheses)
    },
    async toolCalls(id) {
      await delay(150)
      return clone(store(id).toolCalls)
    },
    async approvals(id) {
      await delay(150)
      return clone(store(id).approvals)
    },
    async report(id) {
      await delay(150)
      return clone(store(id).report)
    },
    async requestAction(id, input) {
      await delay()
      const apr: ApprovalRequest = {
        id: uid(),
        investigation_id: id,
        server: "jira",
        tool: "create_issue",
        arguments: { ...input.fields },
        status: "pending",
        requested_by: seed.demoUser,
      }
      store(id).approvals.push(apr)
      emit(id, "approval_requested", { approval_id: apr.id })
      audit("approval.requested", "approval", apr.id)
      return clone(apr)
    },
    subscribeMockEvents(id, afterSeq, onEvent) {
      store(id).events.filter((e) => e.seq > afterSeq).forEach(onEvent)
      subscribers[id] ??= new Set()
      subscribers[id].add(onEvent)
      return () => subscribers[id]?.delete(onEvent)
    },
  },
  approvals: {
    async pending() {
      await delay()
      return clone(Object.values(db.inv).flatMap((s) => s.approvals.filter((a) => a.status === "pending")))
    },
    async approve(id) {
      await delay(800)
      const apr = Object.values(db.inv).flatMap((s) => s.approvals).find((a) => a.id === id) ?? notFound("Approval")
      if (apr.status !== "pending") throw new ApiError(409, "invalid_state", "This approval was already decided")
      apr.status = "executed"
      apr.decided_by = seed.demoUser
      apr.decided_at = new Date().toISOString()
      apr.result = { key: "OPS-1287", url: "https://example.atlassian.net/browse/OPS-1287" }
      audit("approval.approved", "approval", id)
      return clone(apr)
    },
    async reject(id) {
      await delay()
      const apr = Object.values(db.inv).flatMap((s) => s.approvals).find((a) => a.id === id) ?? notFound("Approval")
      apr.status = "rejected"
      apr.decided_by = seed.demoUser
      apr.decided_at = new Date().toISOString()
      audit("approval.rejected", "approval", id)
      return clone(apr)
    },
  },
  integrations: {
    async list() {
      await delay()
      return clone(db.integrations)
    },
    async create(input) {
      await delay()
      const tools =
        input.kind === "jira"
          ? [
              { name: "search_issues", access: "read" as const, enabled: true },
              { name: "get_issue", access: "read" as const, enabled: true },
              { name: "create_issue", access: "write" as const, enabled: false },
            ]
          : []
      const i = { id: uid(), kind: input.kind, status: "connected" as const, config: input.config, last_checked_at: new Date().toISOString(), tools }
      db.integrations.push(i)
      audit("integration.created", "integration", i.id)
      return clone(i)
    },
    async remove(id) {
      await delay()
      db.integrations = db.integrations.filter((i) => i.id !== id)
    },
    async test(id) {
      await delay(900)
      const i = db.integrations.find((x) => x.id === id) ?? notFound("Integration")
      i.last_checked_at = new Date().toISOString()
      audit("integration.tested", "integration", id)
      return clone(i)
    },
    async setToolEnabled(id, tool, enabled) {
      await delay()
      const i = db.integrations.find((x) => x.id === id) ?? notFound("Integration")
      const t = i.tools.find((x) => x.name === tool) ?? notFound("Tool")
      t.enabled = enabled
      return clone(i)
    },
  },
  audit: {
    async list(filters) {
      await delay()
      const items = db.audit
        .filter((e) => !filters?.action || e.action.includes(filters.action))
        .filter((e) => !filters?.actor || (e.actor?.display_name ?? "").toLowerCase().includes(filters.actor.toLowerCase()))
        .filter((e) => !filters?.from || e.created_at >= filters.from)
        .filter((e) => !filters?.to || e.created_at <= filters.to)
      return { items: clone(items), next_cursor: null }
    },
  },
  evaluations: {
    async run(input) {
      await delay()
      const template = seed.evaluationRuns[2]
      const run: EvaluationRun = {
        id: uid(),
        dataset_name: template.dataset_name,
        dataset_version: input.dataset_version ?? template.dataset_version,
        config_label: input.config_label ?? template.config_label,
        config: template.config,
        status: "running",
        started_at: new Date().toISOString(),
      }
      db.runs.unshift(run)
      setTimeout(() => {
        run.status = "completed"
        run.finished_at = new Date().toISOString()
        run.metrics = template.metrics
      }, 4000)
      return clone(run)
    },
    async runs() {
      await delay()
      return clone(db.runs)
    },
    async get(id) {
      await delay()
      const run = db.runs.find((r) => r.id === id) ?? notFound("Evaluation run")
      const qs = [
        "What indicates DB pool contention on orders-api?",
        "Which config change caused INC-2041?",
        "How do I find top connection consumers on RDS?",
        "What is the orders-api request path?",
        "Who is on call for billing-svc this week?",
      ]
      return {
        ...clone(run),
        results: qs.map((q, i) => ({
          question_id: `q-${i}`,
          question: q,
          answerable: i !== 4,
          hit_at_5: i !== 4 && i !== 3,
          reciprocal_rank: i === 4 ? 0 : 1 / (1 + (i % 3)),
          latency_ms: 60 + i * 17,
        })),
      }
    },
  },
  feedback: {
    async send() {
      await delay()
    },
  },
}
