"use client"

import { BarChart3, Loader2, Play } from "lucide-react"
import Link from "next/link"
import { useMemo } from "react"
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { toast } from "sonner"
import { Pill } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { PageHeader } from "@/components/common/page-header"
import { RelativeTime } from "@/components/common/relative-time"
import { ListSkeleton } from "@/components/common/skeletons"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { errorMessage } from "@/lib/api/client"
import { useEvaluationRuns, useRunEvaluation } from "@/lib/api/endpoints/evaluations"
import { absoluteTime, formatMetric } from "@/lib/format"
import type { EvaluationMetrics, EvaluationRun } from "@/lib/types/api"

const QUALITY: { key: keyof EvaluationMetrics; label: string }[] = [
  { key: "recall_at_5", label: "Recall@5" },
  { key: "recall_at_10", label: "Recall@10" },
  { key: "mrr", label: "MRR" },
  { key: "ndcg_at_10", label: "nDCG@10" },
]

const TABLE_METRICS: { key: keyof EvaluationMetrics; label: string; kind?: "ms" }[] = [
  { key: "recall_at_5", label: "R@5" },
  { key: "recall_at_10", label: "R@10" },
  { key: "precision_at_5", label: "P@5" },
  { key: "mrr", label: "MRR" },
  { key: "ndcg_at_10", label: "nDCG@10" },
  { key: "latency_p50_ms", label: "p50", kind: "ms" },
  { key: "latency_p95_ms", label: "p95", kind: "ms" },
]

/** Latest completed run per config, within the most recent dataset version. */
function comparisonSet(runs: EvaluationRun[]) {
  const done = runs.filter((r) => r.status === "completed" && r.metrics)
  if (!done.length) return { version: null as string | null, runs: [] as EvaluationRun[], latest: null as string | null }
  const latestRun = [...done].sort((a, b) => (b.finished_at ?? b.started_at).localeCompare(a.finished_at ?? a.started_at))[0]
  const version = latestRun.dataset_version
  const byConfig = new Map<string, EvaluationRun>()
  for (const r of done.filter((r) => r.dataset_version === version).sort((a, b) => a.started_at.localeCompare(b.started_at))) byConfig.set(r.config_label, r)
  const set = [...byConfig.values()]
  const latest = set.map((r) => r.finished_at ?? r.started_at).sort().at(-1) ?? null
  return { version, runs: set, latest }
}

function Caption({ version, at, dataset }: { version: string; at: string | null; dataset: string }) {
  return (
    <p className="font-mono text-[11px] text-muted-foreground">
      dataset {dataset}@{version}
      {at ? ` · runs up to ${absoluteTime(at)}` : ""}
    </p>
  )
}

export default function EvaluationsPage() {
  const runs = useEvaluationRuns()
  const runEval = useRunEvaluation()
  const all = useMemo(() => runs.data ?? [], [runs.data])
  const cmp = useMemo(() => comparisonSet(all), [all])

  const config: ChartConfig = Object.fromEntries(cmp.runs.map((r, i) => [`c${i}`, { label: r.config_label, color: `var(--chart-${(i % 5) + 1})` }]))
  const qualityData = QUALITY.map((m) => ({ metric: m.label, ...Object.fromEntries(cmp.runs.map((r, i) => [`c${i}`, r.metrics?.[m.key] ?? null])) }))
  const latencyConfig: ChartConfig = { p50: { label: "p50", color: "var(--chart-1)" }, p95: { label: "p95", color: "var(--chart-3)" } }
  const latencyData = cmp.runs.map((r) => ({ config: r.config_label, p50: r.metrics?.latency_p50_ms ?? null, p95: r.metrics?.latency_p95_ms ?? null }))
  const dataset = cmp.runs[0]?.dataset_name ?? ""

  const start = () =>
    runEval.mutate(
      {},
      {
        onSuccess: () => toast.success("Evaluation run started"),
        onError: (e) => toast.error(errorMessage(e)),
      },
    )

  const runButton = (
    <Button onClick={start} disabled={runEval.isPending}>
      {runEval.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run evaluation
    </Button>
  )

  return (
    <>
      <PageHeader title="Evaluations" description="Measured retrieval quality across strategies. Only real, completed runs are shown." actions={all.length > 0 && runButton} />
      {runs.isLoading ? (
        <ListSkeleton rows={6} />
      ) : runs.isError ? (
        <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
      ) : all.length === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No evaluation runs yet"
          description="Run the evaluation suite to compare Lexical, Vector, Hybrid RRF and Hybrid + Rerank on your dataset. Results appear here once measured."
          action={runButton}
        />
      ) : (
        <div className="space-y-4">
          {cmp.version && cmp.runs.length > 0 ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle>Retrieval quality by strategy</CardTitle>
                  <CardDescription>
                    <Caption version={cmp.version} at={cmp.latest} dataset={dataset} />
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ChartContainer config={config} className="aspect-auto h-[280px] w-full">
                    <BarChart data={qualityData} margin={{ left: -16 }}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="metric" tickLine={false} axisLine={false} />
                      <YAxis domain={[0, 1]} tickLine={false} axisLine={false} tickCount={6} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <ChartLegend content={<ChartLegendContent />} />
                      {cmp.runs.map((_, i) => (
                        <Bar key={i} dataKey={`c${i}`} fill={`var(--color-c${i})`} radius={3} />
                      ))}
                    </BarChart>
                  </ChartContainer>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Retrieval latency</CardTitle>
                  <CardDescription>
                    <Caption version={cmp.version} at={cmp.latest} dataset={dataset} />
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ChartContainer config={latencyConfig} className="aspect-auto h-[280px] w-full">
                    <BarChart data={latencyData} margin={{ left: -8 }}>
                      <CartesianGrid vertical={false} />
                      <XAxis dataKey="config" tickLine={false} axisLine={false} interval={0} tickFormatter={(v: string) => (v.length > 14 ? `${v.slice(0, 13)}…` : v)} />
                      <YAxis tickLine={false} axisLine={false} unit=" ms" width={64} />
                      <ChartTooltip content={<ChartTooltipContent />} />
                      <ChartLegend content={<ChartLegendContent />} />
                      <Bar dataKey="p50" fill="var(--color-p50)" radius={3} />
                      <Bar dataKey="p95" fill="var(--color-p95)" radius={3} />
                    </BarChart>
                  </ChartContainer>
                </CardContent>
              </Card>
            </div>
          ) : (
            <EmptyState icon={BarChart3} title="No completed runs yet" description="Charts appear when at least one run has finished." />
          )}

          <Card>
            <CardHeader>
              <CardTitle>All runs</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Config</TableHead>
                    <TableHead>Dataset</TableHead>
                    <TableHead>Status</TableHead>
                    {TABLE_METRICS.map((m) => (
                      <TableHead key={m.key} className="text-right">
                        {m.label}
                      </TableHead>
                    ))}
                    <TableHead>Started</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {all.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>
                        <Link href={`/evaluations/${r.id}`} className="font-medium hover:underline">
                          {r.config_label}
                        </Link>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {r.dataset_name}@{r.dataset_version}
                      </TableCell>
                      <TableCell>
                        <Pill tone={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "info"} icon={r.status === "running" ? <Loader2 className="size-3 animate-spin" /> : undefined}>
                          {r.status}
                        </Pill>
                      </TableCell>
                      {TABLE_METRICS.map((m) => (
                        <TableCell key={m.key} className="text-right font-mono text-xs tabular-nums">
                          {formatMetric(r.metrics?.[m.key], m.kind ?? "ratio")}
                        </TableCell>
                      ))}
                      <TableCell className="text-xs text-muted-foreground">
                        <RelativeTime iso={r.started_at} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </div>
      )}
    </>
  )
}
