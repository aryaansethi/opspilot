"use client"

import { AlertTriangle, ExternalLink, FileText, Lightbulb, Radio, SquareKanban, XCircle } from "lucide-react"
import Link from "next/link"
import { use, useMemo, useState } from "react"
import { InvestigationStateBadge, isRunning, sourceMeta } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { RelativeTime } from "@/components/common/relative-time"
import { ListSkeleton } from "@/components/common/skeletons"
import { ActivityTimeline } from "@/components/investigation/activity-timeline"
import { ApprovalCard } from "@/components/investigation/approval-card"
import { EvidenceCard } from "@/components/investigation/evidence-card"
import { FeedbackButtons } from "@/components/investigation/feedback-buttons"
import { HypothesisCard } from "@/components/investigation/hypothesis-card"
import { JiraDialog } from "@/components/investigation/jira-dialog"
import { ParametersForm } from "@/components/investigation/parameters-form"
import { ReportView } from "@/components/investigation/report-view"
import { StateStepper } from "@/components/investigation/state-stepper"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  useEvidence,
  useHypotheses,
  useInvestigation,
  useInvestigationApprovals,
  useReport,
  useToolCalls,
} from "@/lib/api/endpoints/investigations"
import { shortTime } from "@/lib/format"
import { useInvestigationEvents } from "@/lib/sse"
import type { SourceSystem } from "@/lib/types/api"
import { cn } from "@/lib/utils"

const FAILURE_COPY: Record<string, string> = {
  FAILED_INVALID_PARAMS: "The parameters couldn't be validated. Check the service name and time range, then start a new investigation.",
  FAILED_LLM: "The language model didn't return a usable result. Evidence gathered so far is kept below. Try again in a few minutes.",
  FAILED_RETRIEVAL: "Knowledge-base retrieval failed. Check that documents are indexed and the search service is healthy.",
}

export default function InvestigationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params)
  const inv = useInvestigation(id)
  const evidence = useEvidence(id)
  const hypotheses = useHypotheses(id)
  const tools = useToolCalls(id)
  const approvals = useInvestigationApprovals(id)
  const report = useReport(id)
  const { events, status: streamStatus } = useInvestigationEvents(id)
  const [tab, setTab] = useState("evidence")
  const [sourceFilter, setSourceFilter] = useState<SourceSystem | "all">("all")
  const [highlight, setHighlight] = useState<string | null>(null)
  const [jiraOpen, setJiraOpen] = useState(false)

  const evidenceList = useMemo(() => evidence.data ?? [], [evidence.data])
  const evidenceIndex = useMemo(() => new Map(evidenceList.map((e, i) => [e.id, i + 1])), [evidenceList])

  const openEvidence = (evId: string) => {
    setTab("evidence")
    setSourceFilter("all")
    setHighlight(evId)
    requestAnimationFrame(() => document.getElementById(`evidence-${evId}`)?.scrollIntoView({ behavior: "smooth", block: "center" }))
    setTimeout(() => setHighlight((h) => (h === evId ? null : h)), 2500)
  }

  if (inv.isLoading) return <ListSkeleton rows={8} />
  if (inv.isError) return <ErrorState error={inv.error} onRetry={() => inv.refetch()} />
  const i = inv.data!
  const running = isRunning(i.state)
  const failed = i.state.startsWith("FAILED")
  const sources = Array.from(new Set(evidenceList.map((e) => e.source_system)))
  const shown = sourceFilter === "all" ? evidenceList : evidenceList.filter((e) => e.source_system === sourceFilter)
  const pendingApprovals = (approvals.data ?? []).filter((a) => a.status === "pending")
  const kbCount = evidenceList.filter((e) => !sourceMeta[e.source_system].live).length

  return (
    <div className="space-y-4">
      {/* Banners */}
      {i.state === "PARTIAL" && (
        <div role="status" className="flex gap-3 rounded-lg border border-warning/30 bg-warning/10 p-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <div className="text-sm">
            <p className="font-medium text-warning">Partial investigation — some steps didn&apos;t complete</p>
            <ul className="mt-1 list-disc pl-4 text-muted-foreground">
              {(i.failed_steps?.length ? i.failed_steps : ["One or more tools failed"]).map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <p className="mt-1 text-muted-foreground">Findings below are based only on the evidence that was collected.</p>
          </div>
        </div>
      )}
      {failed && (
        <div role="alert" className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3">
          <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden />
          <div className="text-sm">
            <p className="font-medium text-destructive">Investigation failed</p>
            <p className="mt-1 text-muted-foreground">{FAILURE_COPY[i.state]}</p>
            <Button size="sm" variant="outline" className="mt-2" asChild>
              <Link href="/investigations/new">Start a new investigation</Link>
            </Button>
          </div>
        </div>
      )}

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 xl:grid-cols-[300px_minmax(0,1fr)_320px]">
        {/* Left: question, stepper, live activity */}
        <div className="space-y-4">
          <Card>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between gap-2">
                <InvestigationStateBadge state={i.state} />
                <span className={cn("flex items-center gap-1 text-[11px]", streamStatus === "open" ? "text-success" : "text-muted-foreground")} title="Live updates">
                  <Radio className="size-3" aria-hidden /> {streamStatus === "open" ? "Live" : streamStatus}
                </span>
              </div>
              <p className="text-sm font-medium leading-snug">{i.question}</p>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <dt className="text-muted-foreground">Service</dt>
                  <dd className="font-mono">{i.service ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Environment</dt>
                  <dd>{i.environment ?? "—"}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted-foreground">Time window</dt>
                  <dd className="font-mono">{i.time_start && i.time_end ? `${shortTime(i.time_start)} → ${shortTime(i.time_end)}` : "—"}</dd>
                </div>
                {i.incident_type && (
                  <div>
                    <dt className="text-muted-foreground">Type</dt>
                    <dd className="font-mono">{i.incident_type}</dd>
                  </div>
                )}
                <div>
                  <dt className="text-muted-foreground">Started</dt>
                  <dd>
                    <RelativeTime iso={i.created_at} />
                  </dd>
                </div>
              </dl>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Progress</CardTitle>
            </CardHeader>
            <CardContent>
              <StateStepper state={i.state} events={events} failedSteps={i.failed_steps} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Activity</CardTitle>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[420px] pr-2">
                <ActivityTimeline events={events} toolCalls={tools.data ?? []} />
              </ScrollArea>
            </CardContent>
          </Card>
        </div>

        {/* Center: evidence / hypotheses / report */}
        <Card className="min-w-0">
          <CardContent>
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="w-full sm:w-auto">
                <TabsTrigger value="evidence">
                  <FileText /> Evidence <span className="text-muted-foreground tabular-nums">{evidenceList.length}</span>
                </TabsTrigger>
                <TabsTrigger value="hypotheses">
                  <Lightbulb /> Hypotheses <span className="text-muted-foreground tabular-nums">{hypotheses.data?.length ?? 0}</span>
                </TabsTrigger>
                <TabsTrigger value="report">Report</TabsTrigger>
              </TabsList>

              <TabsContent value="evidence" className="mt-4">
                {evidence.isLoading ? (
                  <ListSkeleton rows={4} />
                ) : evidence.isError ? (
                  <ErrorState error={evidence.error} onRetry={() => evidence.refetch()} />
                ) : evidenceList.length === 0 ? (
                  <EmptyState
                    icon={FileText}
                    title={running ? "Gathering evidence…" : "No evidence collected"}
                    description={running ? "Results from the knowledge base and live tools will appear here as they arrive." : i.state === "AWAITING_PARAMETERS" ? "Provide the missing details to continue." : undefined}
                  />
                ) : (
                  <>
                    <div className="mb-3 flex flex-wrap items-center gap-1.5">
                      <span className="mr-1 text-xs text-muted-foreground">
                        {kbCount} from knowledge base · {evidenceList.length - kbCount} from live tools
                      </span>
                      {(["all", ...sources] as const).map((s) => (
                        <Button key={s} size="xs" variant={sourceFilter === s ? "secondary" : "ghost"} aria-pressed={sourceFilter === s} onClick={() => setSourceFilter(s)}>
                          {s === "all" ? "All" : sourceMeta[s].label}
                        </Button>
                      ))}
                    </div>
                    <div className="space-y-2.5">
                      {shown.map((e) => (
                        <EvidenceCard key={e.id} evidence={e} index={evidenceIndex.get(e.id)} highlighted={highlight === e.id} />
                      ))}
                    </div>
                  </>
                )}
              </TabsContent>

              <TabsContent value="hypotheses" className="mt-4">
                {hypotheses.isLoading ? (
                  <ListSkeleton rows={3} />
                ) : hypotheses.isError ? (
                  <ErrorState error={hypotheses.error} onRetry={() => hypotheses.refetch()} />
                ) : (hypotheses.data ?? []).length === 0 ? (
                  <EmptyState icon={Lightbulb} title={running ? "Not analysed yet" : "No hypotheses"} description="Hypotheses are formed only after evidence is collected and normalised." />
                ) : (
                  <div className="space-y-3">
                    <p className="text-xs text-muted-foreground">These are hypotheses, not conclusions. Each lists the evidence for and against it and what would confirm it.</p>
                    {hypotheses.data?.map((h) => (
                      <HypothesisCard key={h.id} h={h} evidenceIndex={evidenceIndex} onOpenEvidence={openEvidence} />
                    ))}
                  </div>
                )}
              </TabsContent>

              <TabsContent value="report" className="mt-4">
                {report.isLoading ? (
                  <ListSkeleton rows={4} />
                ) : report.isError ? (
                  <ErrorState error={report.error} onRetry={() => report.refetch()} />
                ) : !report.data ? (
                  <EmptyState icon={FileText} title={running ? "Report not ready yet" : "No report"} description={running ? "The report is generated after citations are checked." : undefined} />
                ) : (
                  <>
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                      <FeedbackButtons targetType="report" targetId={i.id} />
                      <Button size="sm" variant="outline" asChild>
                        <Link href={`/investigations/${i.id}/report`}>
                          Full report <ExternalLink />
                        </Link>
                      </Button>
                    </div>
                    <ReportView report={report.data} evidenceIndex={evidenceIndex} onOpenEvidence={openEvidence} />
                  </>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        {/* Right: actions */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {i.state === "AWAITING_PARAMETERS" && <ParametersForm investigation={i} />}

              {pendingApprovals.length > 0 && (
                <div className="space-y-2">
                  <p className="text-xs font-medium text-warning">Awaiting your approval</p>
                  {pendingApprovals.map((a) => (
                    <ApprovalCard key={a.id} approval={a} />
                  ))}
                </div>
              )}

              {report.data && (
                <Button variant="outline" className="w-full" onClick={() => setJiraOpen(true)}>
                  <SquareKanban /> Create Jira ticket
                </Button>
              )}

              {!report.data && i.state !== "AWAITING_PARAMETERS" && pendingApprovals.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  {running ? "Actions become available once the report is ready." : "No actions available."} Write actions always require explicit approval.
                </p>
              )}

              {(approvals.data ?? []).filter((a) => a.status !== "pending").length > 0 && (
                <div className="space-y-2 pt-2">
                  <p className="text-xs font-medium text-muted-foreground">History</p>
                  {approvals.data
                    ?.filter((a) => a.status !== "pending")
                    .map((a) => (
                      <ApprovalCard key={a.id} approval={a} />
                    ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {report.data && <JiraDialog open={jiraOpen} onOpenChange={setJiraOpen} investigation={i} report={report.data} />}
    </div>
  )
}
