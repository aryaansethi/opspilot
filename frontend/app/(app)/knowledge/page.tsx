"use client"

import { BookOpen, Eye, MoreHorizontal, RefreshCw, Trash2, Upload } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { toast } from "sonner"
import { DocStatusBadge, SourceTypeBadge } from "@/components/common/badges"
import { ConfirmDialog } from "@/components/common/confirm-dialog"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { FilterSelect } from "@/components/common/filter-select"
import { PageHeader } from "@/components/common/page-header"
import { RelativeTime } from "@/components/common/relative-time"
import { ListSkeleton } from "@/components/common/skeletons"
import { UploadDialog } from "@/components/knowledge/upload-dialog"
import { Button } from "@/components/ui/button"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { errorMessage } from "@/lib/api/client"
import { useDeleteDocument, useDocuments, useReindexDocument } from "@/lib/api/endpoints/documents"
import { formatBytes } from "@/lib/format"
import type { DocStatus, Document, SourceType } from "@/lib/types/api"

export default function KnowledgePage() {
  const [sourceType, setSourceType] = useState<SourceType>()
  const [status, setStatus] = useState<DocStatus>()
  const [service, setService] = useState("")
  const [uploadOpen, setUploadOpen] = useState(false)
  const [toDelete, setToDelete] = useState<Document | null>(null)
  const docs = useDocuments({ source_type: sourceType, status, service: service.trim() || undefined })
  const del = useDeleteDocument()
  const reindex = useReindexDocument()
  const items = docs.data?.items ?? []
  const filtered = !!(sourceType || status || service)

  const doDelete = async () => {
    if (!toDelete) return
    try {
      await del.mutateAsync(toDelete.id)
      toast.success("Document and its chunks deleted")
      setToDelete(null)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  const doReindex = async (d: Document) => {
    try {
      await reindex.mutateAsync(d.id)
      toast.success(`Re-indexing ${d.title}`)
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <>
      <PageHeader
        title="Knowledge base"
        description="Runbooks, architecture docs and incident reports that OpsPilot searches during investigations."
        actions={
          <Button onClick={() => setUploadOpen(true)}>
            <Upload /> Upload
          </Button>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FilterSelect
          label="Filter by type"
          allLabel="All types"
          value={sourceType}
          onChange={setSourceType}
          options={[
            { value: "runbook", label: "Runbook" },
            { value: "architecture", label: "Architecture" },
            { value: "incident_report", label: "Incident report" },
            { value: "other", label: "Other" },
          ]}
        />
        <FilterSelect
          label="Filter by status"
          allLabel="All statuses"
          value={status}
          onChange={setStatus}
          options={[
            { value: "indexed", label: "Indexed" },
            { value: "processing", label: "Processing" },
            { value: "queued", label: "Queued" },
            { value: "failed", label: "Failed" },
          ]}
        />
        <Input value={service} onChange={(e) => setService(e.target.value)} placeholder="Service…" aria-label="Filter by service" className="h-7 w-40" />
      </div>

      {docs.isLoading ? (
        <ListSkeleton rows={6} />
      ) : docs.isError ? (
        <ErrorState error={docs.error} onRetry={() => docs.refetch()} />
      ) : items.length === 0 ? (
        filtered ? (
          <EmptyState icon={BookOpen} title="No documents match these filters" />
        ) : (
          <EmptyState
            icon={Upload}
            title="Upload your first runbook"
            description="Add runbooks, architecture notes and postmortems. They're chunked, embedded and indexed for hybrid search."
            action={<Button onClick={() => setUploadOpen(true)}>Upload documents</Button>}
          />
        )
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead className="hidden md:table-cell">Type</TableHead>
                <TableHead className="hidden lg:table-cell">Service</TableHead>
                <TableHead className="hidden lg:table-cell">Env</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="hidden text-right sm:table-cell">Chunks</TableHead>
                <TableHead className="hidden md:table-cell">Indexed</TableHead>
                <TableHead className="w-10">
                  <span className="sr-only">Actions</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="max-w-[280px]">
                    <Link href={`/knowledge/${d.id}`} className="block truncate font-medium hover:underline">
                      {d.title}
                    </Link>
                    <span className="text-xs text-muted-foreground">{formatBytes(d.size_bytes)}</span>
                    {d.status === "failed" && d.error && <p className="truncate text-xs text-destructive">{d.error}</p>}
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <SourceTypeBadge type={d.source_type} />
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs lg:table-cell">{d.service ?? "—"}</TableCell>
                  <TableCell className="hidden text-xs lg:table-cell">{d.environment ?? "—"}</TableCell>
                  <TableCell>
                    <DocStatusBadge status={d.status} />
                  </TableCell>
                  <TableCell className="hidden text-right tabular-nums sm:table-cell">{d.chunk_count}</TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground md:table-cell">{d.indexed_at ? <RelativeTime iso={d.indexed_at} /> : "—"}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${d.title}`}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link href={`/knowledge/${d.id}`}>
                            <Eye /> View
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => void doReindex(d)} disabled={d.status === "queued" || d.status === "processing"}>
                          <RefreshCw /> Re-index
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem variant="destructive" onSelect={() => setToDelete(d)}>
                          <Trash2 /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <ConfirmDialog
        open={!!toDelete}
        onOpenChange={(v) => !v && setToDelete(null)}
        title="Delete document?"
        description={
          <>
            <span className="font-medium text-foreground">{toDelete?.title}</span> and all of its chunks will be removed from the lexical and vector
            indexes. This can&apos;t be undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        busy={del.isPending}
        onConfirm={doDelete}
      />
    </>
  )
}
