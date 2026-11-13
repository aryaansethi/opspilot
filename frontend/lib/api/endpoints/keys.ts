import type { AuditFilters } from "@/lib/types/api"
import type { DocumentListParams, InvestigationListParams } from "../contract"

/** Query keys are prefixed with the workspace so switching workspaces never shows stale tenant data. */
export const qk = {
  me: ["me"] as const,
  workspaces: ["workspaces"] as const,
  documents: (ws: string | null, p?: DocumentListParams) => ["ws", ws, "documents", p ?? {}] as const,
  document: (ws: string | null, id: string) => ["ws", ws, "document", id] as const,
  documentChunks: (ws: string | null, id: string) => ["ws", ws, "document", id, "chunks"] as const,
  investigations: (ws: string | null, p?: InvestigationListParams) => ["ws", ws, "investigations", p ?? {}] as const,
  investigation: (ws: string | null, id: string) => ["ws", ws, "investigation", id] as const,
  investigationPart: (ws: string | null, id: string, part: string) => ["ws", ws, "investigation", id, part] as const,
  pendingApprovals: (ws: string | null) => ["ws", ws, "approvals", "pending"] as const,
  integrations: (ws: string | null) => ["ws", ws, "integrations"] as const,
  audit: (ws: string | null, f?: AuditFilters) => ["ws", ws, "audit", f ?? {}] as const,
  evalRuns: (ws: string | null) => ["ws", ws, "evaluations"] as const,
  evalRun: (ws: string | null, id: string) => ["ws", ws, "evaluation", id] as const,
}
