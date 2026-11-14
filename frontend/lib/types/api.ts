// Mirror of the backend API contract (ARCHITECTURE.md §6).
// Replace with `openapi-typescript` output once the backend publishes its schema.

export type UUID = string
export type ISODate = string

export interface User {
  id: UUID
  email: string
  display_name: string
}

export interface Workspace {
  id: UUID
  name: string
  slug: string
  role: "owner" | "member" | "viewer"
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}

export interface AuthResponse {
  access_token: string
  user: User
}

export type SourceType = "runbook" | "architecture" | "incident_report" | "other"
export type DocStatus = "pending_upload" | "queued" | "processing" | "indexed" | "failed"

export interface Document {
  id: UUID
  title: string
  source_type: SourceType
  service?: string
  environment?: string
  mime_type: string
  size_bytes: number
  status: DocStatus
  error?: string
  chunk_count: number
  indexed_at?: ISODate
  created_at: ISODate
  embedding_model?: string
}

export interface DocumentChunk {
  id: UUID
  chunk_index: number
  section_path?: string
  page_start?: number
  page_end?: number
  excerpt: string
}

export interface DocumentStatus {
  status: DocStatus
  error?: string
  chunk_count: number
  indexed_at?: ISODate
}

export interface UploadUrlRequest {
  filename: string
  mime_type: string
  size_bytes: number
  source_type: SourceType
  service?: string
  environment?: string
}

export interface UploadUrlResponse {
  document_id: UUID
  upload_url: string
  headers: Record<string, string>
}

export interface SearchDebug {
  lexical_rank: number | null
  vector_rank: number | null
  rrf_score: number
  rerank_score: number | null
}

export interface SearchResult {
  chunk_id: UUID
  document_id: UUID
  document_title: string
  source_type: SourceType
  excerpt: string
  section_path?: string
  page_start?: number
  page_end?: number
  score: number
  debug?: SearchDebug
}

export type SearchMode = "hybrid" | "lexical" | "vector"

export interface SearchFilters {
  source_type?: SourceType
  service?: string
  environment?: string
}

export interface SearchRequest {
  query: string
  filters?: SearchFilters
  top_k: number
  mode: SearchMode
  rerank: boolean
}

export interface SearchResponse {
  results: SearchResult[]
  latency_ms: number
}

export type SourceSystem = "knowledge_base" | "github" | "cloudwatch" | "jira"

export interface Evidence {
  id: UUID
  /** Stable per-investigation label ("E1", "E2", …) used in report citations. */
  label?: string
  source_system: SourceSystem
  title: string
  source_reference: string
  url?: string
  excerpt: string
  observed_at?: ISODate
  time_range?: { start: ISODate; end: ISODate }
  retrieval_method?: string
  rank?: number
  reliability_notes?: string
  metadata: Record<string, unknown>
}

export interface AskResponse {
  answer: string
  claims: { text: string; evidence_ids: UUID[] }[]
  citations: Evidence[]
  insufficient_evidence: boolean
}

export type InvestigationState =
  | "RECEIVED"
  | "CLASSIFY_REQUEST"
  | "COLLECT_PARAMETERS"
  | "AWAITING_PARAMETERS"
  | "PLAN_INVESTIGATION"
  | "RUN_KNOWLEDGE_RETRIEVAL"
  | "RUN_READ_TOOLS"
  | "NORMALIZE_EVIDENCE"
  | "ANALYZE_HYPOTHESES"
  | "CHECK_CITATIONS"
  | "GENERATE_REPORT"
  | "AWAITING_ACTION"
  | "COMPLETED"
  | "PARTIAL"
  | "FAILED_INVALID_PARAMS"
  | "FAILED_LLM"
  | "FAILED_RETRIEVAL"

export type MissingParameter = "service" | "environment" | "time_range"

export interface Investigation {
  id: UUID
  question: string
  service?: string
  environment?: string
  time_start?: ISODate
  time_end?: ISODate
  incident_type?: string
  state: InvestigationState
  missing_parameters?: MissingParameter[]
  failed_steps?: string[]
  error?: string | null
  plan?: { tasks?: string[]; log_search_terms?: string[]; rationale?: string; source?: "llm" | "default"; allowed_tasks?: string[] } | null
  created_by: User | null
  created_at: ISODate
  updated_at: ISODate
}

export interface CreateInvestigationRequest {
  question: string
  service?: string
  environment?: string
  time_start?: ISODate
  time_end?: ISODate
}

export interface ContinueInvestigationRequest {
  service?: string
  environment?: string
  time_start?: ISODate
  time_end?: ISODate
}

export interface Hypothesis {
  id: UUID
  statement: string
  status: "proposed" | "supported" | "refuted" | "confirmed"
  supporting_evidence_ids: UUID[]
  contradicting_evidence_ids: UUID[]
  missing_evidence: string[]
  confidence_explanation: string
  validation_steps: string[]
}

export interface ToolCall {
  id: UUID
  server: string
  tool: string
  access: "read" | "write"
  arguments_redacted: Record<string, unknown>
  status: "running" | "succeeded" | "failed" | "timeout" | "denied"
  duration_ms?: number
  result_bytes?: number
  error?: string | null
  truncated?: boolean
  started_at: ISODate
}

export interface ApprovalRequest {
  id: UUID
  investigation_id: UUID
  tool: string
  server: string
  arguments: Record<string, unknown>
  kind?: string
  status: "pending" | "approved" | "rejected" | "executed" | "failed"
  requested_by: User | null
  decided_by?: User | null
  decided_at?: ISODate | null
  result?: { url?: string; key?: string } | null
  /** Why execution failed (e.g. the target tool isn't registered). */
  error?: string | null
  created_at?: ISODate
}

export interface JiraIssueFields {
  project: string
  issue_type: string
  summary: string
  description: string
  labels: string[]
}

export interface ActionRequest {
  kind: "create_jira_issue"
  fields: JiraIssueFields
}

export interface Report {
  investigation_id: UUID
  version: number
  overview: string
  scope: string
  observed_facts: { text: string; evidence_ids: UUID[] }[]
  hypotheses: Hypothesis[]
  recommended_diagnostics: string[]
  proposed_remediation: string[]
  unknowns: string[]
  /** Model statements dropped by citation/number validation, kept for transparency. */
  removed_by_validation?: { kind: "fact" | "hypothesis"; text: string; reason: string; cited?: string[] }[]
  tool_summary: { total: number; succeeded: number; failed: number }
  markdown: string
  generated_at: ISODate
}

export type InvestigationEventType =
  | "state_changed"
  | "step_started"
  | "step_completed"
  | "step_failed"
  | "tool_call_started"
  | "tool_call_completed"
  | "evidence_added"
  | "hypothesis_added"
  | "report_ready"
  | "approval_requested"
  | "parameters_required"
  | "error"

export interface InvestigationEvent {
  seq: number
  type: InvestigationEventType
  payload: Record<string, unknown>
  at: ISODate
}

export type IntegrationKind = "github" | "cloudwatch" | "jira"

export interface Integration {
  id: UUID
  kind: IntegrationKind
  status: "connected" | "error" | "disabled"
  config: Record<string, unknown>
  last_checked_at?: ISODate
  tools: { name: string; access: "read" | "write"; enabled: boolean }[]
}

export interface CreateIntegrationRequest {
  kind: IntegrationKind
  config: Record<string, unknown>
  secret?: string
}

export interface AuditEvent {
  id: UUID
  actor: User | null
  action: string
  target_type: string
  target_id: UUID | null
  metadata: Record<string, unknown>
  created_at: ISODate
}

export interface AuditFilters {
  actor?: string
  action?: string
  from?: ISODate
  to?: ISODate
  cursor?: string
}

export type EvaluationKind = "retrieval" | "answers"
export type EvaluationSplit = "test" | "tune" | "all"
export type QuestionKind = "lexical" | "semantic" | "multi" | "unanswerable"

export interface KindBreakdown {
  n: number
  recall_at_5: number
  mrr: number
}

/** Retrieval runs fill the ranking metrics; answers runs fill the answer metrics. Faithfulness isn't measured. */
export interface EvaluationMetrics {
  // retrieval
  recall_at_5?: number
  recall_at_10?: number
  precision_at_5?: number
  mrr?: number
  ndcg_at_5?: number
  ndcg_at_10?: number
  answerable_questions?: number
  by_kind?: Partial<Record<"lexical" | "semantic" | "multi", KindBreakdown>>
  // answers
  abstention_accuracy?: number
  unanswerable_abstention_rate?: number
  citation_precision?: number
  citation_coverage?: number
  expected_fact_match?: number
  model_errors?: number
  // both
  questions?: number
  latency_p50_ms?: number
  latency_p95_ms?: number
}

export interface EvaluationRun {
  id: UUID
  dataset_name: string
  dataset_version: string
  dataset_hash?: string
  kind?: EvaluationKind
  config_label: string
  config: Record<string, unknown>
  split?: EvaluationSplit
  status: "running" | "completed" | "failed"
  started_at: ISODate
  finished_at?: ISODate | null
  metrics?: EvaluationMetrics | null
  error?: string | null
}

export interface EvaluationQuestionResult {
  /** Dataset question id, e.g. "q012". */
  question_id: string
  question: string
  kind?: QuestionKind
  answerable: boolean
  hit_at_5: boolean
  reciprocal_rank: number
  latency_ms: number
  detail?: Record<string, unknown>
}

export interface EvaluationRunDetail extends EvaluationRun {
  results: EvaluationQuestionResult[]
}

export interface RunEvaluationRequest {
  dataset_version?: string
  /** Omit to queue all four retrieval configs. */
  config_label?: string
  split?: EvaluationSplit
  /** Answers runs only: cap the number of questions. */
  limit?: number
}

export interface FeedbackRequest {
  target_type: "report" | "answer" | "evidence"
  target_id: UUID
  rating: "up" | "down"
  comment?: string
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: Record<string, unknown> }
}
