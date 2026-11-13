import { refreshAccessToken, request, session, uploadToPresignedUrl } from "./client"
import type { ApiContract } from "./contract"
import type {
  ApprovalRequest,
  AskResponse,
  AuditEvent,
  AuthResponse,
  Document,
  DocumentChunk,
  DocumentStatus,
  EvaluationRun,
  EvaluationRunDetail,
  Evidence,
  Hypothesis,
  Integration,
  Investigation,
  Page,
  Report,
  SearchFilters,
  SearchResponse,
  ToolCall,
  UploadUrlResponse,
  User,
  Workspace,
} from "@/lib/types/api"
import { ApiError } from "./client"

/** The backend takes lists (source_types/services/environments); the UI filters by one value each. */
function toBackendFilters(f?: SearchFilters) {
  if (!f) return undefined
  const out = {
    ...(f.source_type ? { source_types: [f.source_type] } : {}),
    ...(f.service ? { services: [f.service] } : {}),
    ...(f.environment ? { environments: [f.environment] } : {}),
  }
  return Object.keys(out).length ? out : undefined
}

/** Real backend implementation. Paths match ARCHITECTURE.md §6. */
export const httpApi: ApiContract = {
  auth: {
    register: (input) => request<AuthResponse>("/auth/register", { method: "POST", body: input, noRetry: true }),
    login: (input) => request<AuthResponse>("/auth/login", { method: "POST", body: input, noRetry: true }),
    refresh: () => refreshAccessToken(),
    logout: async () => {
      try {
        await request<void>("/auth/logout", { method: "POST", noRetry: true })
      } finally {
        session.setToken(null)
      }
    },
    me: () => request<User>("/auth/me"),
  },
  workspaces: {
    list: () => request<Workspace[]>("/workspaces"),
    create: (input) => request<Workspace>("/workspaces", { method: "POST", body: input }),
  },
  documents: {
    list: (params) => request<Page<Document>>("/documents", { query: { ...params } }),
    get: (id) => request<Document>(`/documents/${id}`),
    chunks: async (id) => {
      // Backend returns the full chunk text as `content`.
      const rows = await request<(Omit<DocumentChunk, "excerpt"> & { content?: string; excerpt?: string })[]>(`/documents/${id}/chunks`)
      return rows.map(({ content, excerpt, ...c }) => ({ ...c, excerpt: excerpt ?? content ?? "" }))
    },
    status: (id) => request<DocumentStatus>(`/documents/${id}/status`),
    uploadUrl: (input) => request<UploadUrlResponse>("/documents/upload-url", { method: "POST", body: input }),
    uploadFile: (target, file, onProgress) => uploadToPresignedUrl(target.upload_url, target.headers, file, onProgress),
    completeUpload: (id) => request<Document>("/documents/complete-upload", { method: "POST", body: { document_id: id } }),
    remove: (id) => request<void>(`/documents/${id}`, { method: "DELETE" }),
    reindex: (id) => request<Document>(`/documents/${id}/reindex`, { method: "POST" }),
  },
  search: {
    search: (input) => request<SearchResponse>("/search", { method: "POST", body: { ...input, filters: toBackendFilters(input.filters) } }),
    debug: (input) => request<SearchResponse>("/search/debug", { method: "POST", body: { ...input, filters: toBackendFilters(input.filters) } }),
    ask: (input) => request<AskResponse>("/ask", { method: "POST", body: { ...input, filters: toBackendFilters(input.filters) } }),
  },
  investigations: {
    list: (params) => request<Page<Investigation>>("/investigations", { query: { ...params } }),
    get: (id) => request<Investigation>(`/investigations/${id}`),
    create: (input) => request<{ id: string }>("/investigations", { method: "POST", body: input }),
    continue: (id, input) => request<Investigation>(`/investigations/${id}/continue`, { method: "POST", body: input }),
    evidence: (id) => request<Evidence[]>(`/investigations/${id}/evidence`),
    hypotheses: (id) => request<Hypothesis[]>(`/investigations/${id}/hypotheses`),
    toolCalls: (id) => request<ToolCall[]>(`/investigations/${id}/tool-calls`),
    approvals: (id) => request<ApprovalRequest[]>(`/investigations/${id}/approvals`),
    report: async (id) => {
      try {
        return await request<Report>(`/investigations/${id}/report`)
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null
        throw err
      }
    },
    requestAction: (id, input) =>
      request<ApprovalRequest>(`/investigations/${id}/actions`, { method: "POST", body: input }),
  },
  approvals: {
    pending: () => request<ApprovalRequest[]>("/approvals", { query: { status: "pending" } }),
    approve: (id) => request<ApprovalRequest>(`/approvals/${id}/approve`, { method: "POST" }),
    reject: (id) => request<ApprovalRequest>(`/approvals/${id}/reject`, { method: "POST" }),
  },
  integrations: {
    list: () => request<Integration[]>("/integrations"),
    create: (input) => request<Integration>("/integrations", { method: "POST", body: input }),
    remove: (id) => request<void>(`/integrations/${id}`, { method: "DELETE" }),
    test: (id) => request<Integration>(`/integrations/${id}/test`, { method: "POST" }),
    setToolEnabled: (id, tool, enabled) =>
      request<Integration>(`/integrations/${id}/tools/${encodeURIComponent(tool)}`, {
        method: "PATCH",
        body: { enabled },
      }),
  },
  audit: {
    list: (filters) => request<Page<AuditEvent>>("/audit-events", { query: { ...filters } }),
  },
  evaluations: {
    run: (input) => request<EvaluationRun>("/evaluations/run", { method: "POST", body: input }),
    runs: () => request<EvaluationRun[]>("/evaluations/runs"),
    get: (id) => request<EvaluationRunDetail>(`/evaluations/runs/${id}`),
  },
  feedback: {
    send: (input) => request<void>("/feedback", { method: "POST", body: input }),
  },
}
