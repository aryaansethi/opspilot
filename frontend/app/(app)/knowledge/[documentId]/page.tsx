"use client"

import { FileText } from "lucide-react"
import { use } from "react"
import { DocStatusBadge, SourceTypeBadge } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { PageHeader } from "@/components/common/page-header"
import { RelativeTime } from "@/components/common/relative-time"
import { ListSkeleton } from "@/components/common/skeletons"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useDocument, useDocumentChunks } from "@/lib/api/endpoints/documents"
import { formatBytes } from "@/lib/format"

export default function DocumentPage({ params }: { params: Promise<{ documentId: string }> }) {
  const { documentId } = use(params)
  const doc = useDocument(documentId)
  const chunks = useDocumentChunks(documentId, doc.data?.status === "indexed")

  if (doc.isLoading) return <ListSkeleton rows={6} />
  if (doc.isError) return <ErrorState error={doc.error} onRetry={() => doc.refetch()} />
  const d = doc.data!

  const meta: [string, React.ReactNode][] = [
    ["Status", <DocStatusBadge key="s" status={d.status} />],
    ["Type", <SourceTypeBadge key="t" type={d.source_type} />],
    ["Service", <span key="sv" className="font-mono text-xs">{d.service ?? "—"}</span>],
    ["Environment", d.environment ?? "—"],
    ["Size", formatBytes(d.size_bytes)],
    ["MIME type", <span key="m" className="font-mono text-xs">{d.mime_type}</span>],
    ["Chunks", d.chunk_count],
    ["Embedding model", <span key="e" className="font-mono text-xs">{d.embedding_model ?? "—"}</span>],
    ["Uploaded", <RelativeTime key="u" iso={d.created_at} />],
    ["Last indexed", d.indexed_at ? <RelativeTime key="i" iso={d.indexed_at} /> : "—"],
    ["Document ID", <span key="id" className="font-mono text-xs break-all">{d.id}</span>],
  ]

  return (
    <>
      <PageHeader title={d.title} />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Metadata</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="space-y-2.5 text-sm">
              {meta.map(([k, v]) => (
                <div key={k} className="flex items-start justify-between gap-4">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
            {d.error && <p className="mt-4 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">{d.error}</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Chunks</CardTitle>
          </CardHeader>
          <CardContent>
            {d.status !== "indexed" ? (
              <EmptyState icon={FileText} title="Not indexed yet" description="Chunks appear here once ingestion finishes." />
            ) : chunks.isLoading ? (
              <ListSkeleton rows={4} />
            ) : chunks.isError ? (
              <ErrorState error={chunks.error} onRetry={() => chunks.refetch()} />
            ) : (chunks.data ?? []).length === 0 ? (
              <EmptyState icon={FileText} title="No chunks" />
            ) : (
              <ol className="space-y-3">
                {chunks.data?.map((c) => (
                  <li key={c.id} className="rounded-md border p-3">
                    <div className="mb-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <span className="font-mono">#{c.chunk_index}</span>
                      {c.section_path && <span>{c.section_path}</span>}
                      {c.page_start !== undefined && (
                        <span>
                          p.{c.page_start}
                          {c.page_end && c.page_end !== c.page_start ? `–${c.page_end}` : ""}
                        </span>
                      )}
                    </div>
                    <p className="text-sm leading-relaxed">{c.excerpt}</p>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
