"use client"

import { Copy, FileText, Printer } from "lucide-react"
import { use, useMemo } from "react"
import { toast } from "sonner"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { PageHeader } from "@/components/common/page-header"
import { ListSkeleton } from "@/components/common/skeletons"
import { EvidenceCard } from "@/components/investigation/evidence-card"
import { ReportView } from "@/components/investigation/report-view"
import { Button } from "@/components/ui/button"
import { useEvidence, useInvestigation, useReport } from "@/lib/api/endpoints/investigations"

export default function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const inv = useInvestigation(id)
  const report = useReport(id)
  const evidence = useEvidence(id)
  const evidenceList = useMemo(() => evidence.data ?? [], [evidence.data])
  const evidenceIndex = useMemo(() => new Map<string, number | string>(evidenceList.map((e, i) => [e.id, e.label ?? i + 1])), [evidenceList])

  const jump = (evId: string) => document.getElementById(`evidence-${evId}`)?.scrollIntoView({ behavior: "smooth", block: "center" })

  const copy = async () => {
    if (!report.data) return
    try {
      await navigator.clipboard.writeText(report.data.markdown)
      toast.success("Markdown copied")
    } catch {
      toast.error("Couldn't access the clipboard")
    }
  }

  if (inv.isLoading || report.isLoading) return <ListSkeleton rows={8} />
  if (inv.isError) return <ErrorState error={inv.error} onRetry={() => inv.refetch()} />
  if (report.isError) return <ErrorState error={report.error} onRetry={() => report.refetch()} />
  if (!report.data) return <EmptyState icon={FileText} title="No report yet" description="The report appears once the investigation reaches the report stage." />

  return (
    <article className="mx-auto max-w-3xl">
      <PageHeader
        title="Incident report"
        description={inv.data?.question}
        actions={
          <div className="no-print flex gap-2">
            <Button variant="outline" size="sm" onClick={copy}>
              <Copy /> Copy markdown
            </Button>
            <Button variant="outline" size="sm" onClick={() => window.print()}>
              <Printer /> Print / PDF
            </Button>
          </div>
        }
      />
      <ReportView report={report.data} evidenceIndex={evidenceIndex} onOpenEvidence={jump} />
      <section className="mt-8">
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Evidence</h3>
        <div className="space-y-2.5">
          {evidenceList.map((e) => (
            <EvidenceCard key={e.id} evidence={e} index={evidenceIndex.get(e.id)} className="break-inside-avoid" />
          ))}
        </div>
      </section>
    </article>
  )
}
