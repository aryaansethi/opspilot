import type {
  ActionRequest,
  ApprovalRequest,
  AskResponse,
  AuditEvent,
  AuditFilters,
  AuthResponse,
  ContinueInvestigationRequest,
  CreateIntegrationRequest,
  CreateInvestigationRequest,
  Document,
  DocumentChunk,
  DocumentStatus,
  DocStatus,
  EvaluationRun,
  EvaluationRunDetail,
  Evidence,
  FeedbackRequest,
  Hypothesis,
  Integration,
  Investigation,
  InvestigationEvent,
  InvestigationState,
  Page,
  Report,
  SearchFilters,
  SearchRequest,
  SearchResponse,
  SourceType,
  ToolCall,
  UploadUrlRequest,
  UploadUrlResponse,
  User,
  UUID,
  Workspace,
} from "@/lib/types/api"

export interface DocumentListParams {
  source_type?: SourceType
  status?: DocStatus
  service?: string
  cursor?: string
  limit?: number
}

export interface InvestigationListParams {
  state?: InvestigationState
  cursor?: string
  limit?: number
}

/**
 * Everything the UI can ask of the backend. Implemented by the HTTP client (lib/api/http)
 * and, for previews only, by the mock adapter (lib/api/mock).
 */
export interface ApiContract {
  auth: {
    register(input: { email: string; password: string; display_name: string }): Promise<AuthResponse>
    login(input: { email: string; password: string }): Promise<AuthResponse>
    refresh(): Promise<boolean>
    logout(): Promise<void>
    me(): Promise<User>
  }
  workspaces: {
    list(): Promise<Workspace[]>
    create(input: { name: string }): Promise<Workspace>
  }
  documents: {
    list(params?: DocumentListParams): Promise<Page<Document>>
    get(id: UUID): Promise<Document>
    chunks(id: UUID): Promise<DocumentChunk[]>
    status(id: UUID): Promise<DocumentStatus>
    uploadUrl(input: UploadUrlRequest): Promise<UploadUrlResponse>
    uploadFile(target: UploadUrlResponse, file: File, onProgress: (pct: number) => void): Promise<void>
    completeUpload(id: UUID): Promise<Document>
    remove(id: UUID): Promise<void>
    reindex(id: UUID): Promise<Document>
  }
  search: {
    search(input: SearchRequest): Promise<SearchResponse>
    debug(input: SearchRequest): Promise<SearchResponse>
    ask(input: { question: string; filters?: SearchFilters }): Promise<AskResponse>
  }
  investigations: {
    list(params?: InvestigationListParams): Promise<Page<Investigation>>
    get(id: UUID): Promise<Investigation>
    create(input: CreateInvestigationRequest): Promise<{ id: UUID }>
    continue(id: UUID, input: ContinueInvestigationRequest): Promise<Investigation>
    evidence(id: UUID): Promise<Evidence[]>
    hypotheses(id: UUID): Promise<Hypothesis[]>
    toolCalls(id: UUID): Promise<ToolCall[]>
    approvals(id: UUID): Promise<ApprovalRequest[]>
    report(id: UUID): Promise<Report | null>
    requestAction(id: UUID, input: ActionRequest): Promise<ApprovalRequest>
    /** Mock-only: stream simulated events. The real stream is consumed in lib/sse.ts. */
    subscribeMockEvents?(
      id: UUID,
      afterSeq: number,
      onEvent: (e: InvestigationEvent) => void,
    ): () => void
  }
  approvals: {
    pending(): Promise<ApprovalRequest[]>
    approve(id: UUID): Promise<ApprovalRequest>
    reject(id: UUID): Promise<ApprovalRequest>
  }
  integrations: {
    list(): Promise<Integration[]>
    create(input: CreateIntegrationRequest): Promise<Integration>
    remove(id: UUID): Promise<void>
    test(id: UUID): Promise<Integration>
    setToolEnabled(id: UUID, tool: string, enabled: boolean): Promise<Integration>
  }
  audit: {
    list(filters?: AuditFilters): Promise<Page<AuditEvent>>
  }
  evaluations: {
    run(input: { dataset_version?: string; config_label?: string }): Promise<EvaluationRun>
    runs(): Promise<EvaluationRun[]>
    get(id: UUID): Promise<EvaluationRunDetail>
  }
  feedback: {
    send(input: FeedbackRequest): Promise<void>
  }
}
