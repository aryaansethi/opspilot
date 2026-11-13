"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { UploadUrlRequest } from "@/lib/types/api"
import type { DocumentListParams } from "../contract"
import { qk } from "./keys"

const isBusy = (s: string) => s === "pending_upload" || s === "queued" || s === "processing"

/** Browsers often report "" for .md files; the backend only accepts these three types. */
function mimeFor(file: File): string {
  const ext = file.name.toLowerCase().split(".").pop()
  if (ext === "pdf") return "application/pdf"
  if (ext === "md" || ext === "markdown") return "text/markdown"
  if (ext === "txt") return "text/plain"
  return file.type || "application/octet-stream"
}

export function useDocuments(params?: DocumentListParams) {
  const ws = useWorkspaceId()
  return useQuery({
    queryKey: qk.documents(ws, params),
    queryFn: () => api.documents.list(params),
    enabled: !!ws,
    // Poll every 3s while anything is still being ingested.
    refetchInterval: (q) => (q.state.data?.items.some((d) => isBusy(d.status)) ? 3000 : false),
  })
}

export function useDocument(id: string) {
  const ws = useWorkspaceId()
  return useQuery({
    queryKey: qk.document(ws, id),
    queryFn: () => api.documents.get(id),
    enabled: !!ws,
    refetchInterval: (q) => (q.state.data && isBusy(q.state.data.status) ? 3000 : false),
  })
}

export function useDocumentChunks(id: string, enabled = true) {
  const ws = useWorkspaceId()
  return useQuery({
    queryKey: qk.documentChunks(ws, id),
    queryFn: () => api.documents.chunks(id),
    enabled: !!ws && enabled,
  })
}

function useInvalidateDocuments() {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return () => qc.invalidateQueries({ queryKey: ["ws", ws, "documents"] })
}

/** Runs the 3-step presigned upload: request URL → PUT to storage → complete. */
export function useUploadDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({
    mutationFn: async ({ file, meta, onProgress }: { file: File; meta: Omit<UploadUrlRequest, "filename" | "mime_type" | "size_bytes">; onProgress: (stage: "uploading" | "finalizing", pct: number) => void }) => {
      const target = await api.documents.uploadUrl({
        filename: file.name,
        mime_type: mimeFor(file),
        size_bytes: file.size,
        ...meta,
      })
      await api.documents.uploadFile(target, file, (pct) => onProgress("uploading", pct))
      onProgress("finalizing", 100)
      return api.documents.completeUpload(target.document_id)
    },
    onSettled: invalidate,
  })
}

export function useDeleteDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({ mutationFn: (id: string) => api.documents.remove(id), onSuccess: invalidate })
}

export function useReindexDocument() {
  const invalidate = useInvalidateDocuments()
  return useMutation({ mutationFn: (id: string) => api.documents.reindex(id), onSuccess: invalidate })
}
