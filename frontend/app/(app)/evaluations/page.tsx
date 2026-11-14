"use client"

import { BarChart3, Info, Loader2, Play } from "lucide-react"
import Link from "next/link"
import { useMemo, useState, type FormEvent } from "react"
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
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { errorMessage } from "@/lib/api/client"
import { useEvaluationRuns, useRunEvaluation } from "@/lib/api/endpoints/evaluations"
import { absoluteTime, formatMetric } from "@/lib/format"
import { ANSWER_METRICS, configName, RETRIEVAL_LABELS, shortName } from "@/lib/evaluations"
import type { EvaluationMetrics, EvaluationRun, EvaluationSplit } from "@/lib/types/api"

const QUALITY: { key: keyof EvaluationMetrics; label: string }[] = [
  { key: "recall_at_5", label: "Recall@5" },
  { key: "recall_at_10", label: "Recall@10" },
  { key: "mrr", label: "MRR" },
  { key: "ndcg_at_10", label: "nDCG@10" },
]

const kindOf = (r: EvaluationRun) => r.kind ?? (r.config_label.startsWith("answers") ? "answers" : "retrieval")
const splitOf = (r: EvaluationRun) => r.split ?? "test"
const finishedAt = (r: EvaluationRun) => r.finished_at ?? r.started_at

/** Latest completed retrieval run per strategy for a split, within the newest dataset version. */
function comparisonSet(runs: EvaluationRun[], split: EvaluationSplit) {
  const done = runs.filter((r) => r.status === "completed" && r.metrics && kindOf(r) === "retrieval" && splitOf(r) === split)
  if (!done.length) return { version: null as string | null, runs: [] as EvaluationRun[], latest: null as string | null }
  const version = [...done].sort((a, b) => finishedAt(b).localeCompare(finishedAt(a)))[0].dataset_version
  const byConfig = new Map<string, EvaluationRun>()
  for (const r of done.filter((r) => r.dataset_version === version).sort((a, b) => a.started_at.localeCompare(b.started_at))) byConfig.set(r.config_label, r)
  const set = [...byConfig.values()].sort((a, b) => a.config_label.localeCompare(b.config_label))
  const latest = set.map(finishedAt).sort().at(-1) ?? null
  return { version, runs: set, latest }
}

function Caption({ run, at, split }: { run: EvaluationRun; at: string | null; split: string }) {
  return (
    <p className="font-mono text-[11px] text-muted-foreground">
      dataset {run.dataset_name}@{run.dataset_version}
      {run.dataset_hash ? ` (${run.dataset_hash.slice(0, 8)})` : ""} · {split} split
      {at ? ` · runs up to ${absoluteTime(at)}` : ""}
    </p>
  )
}

function headline(r: EvaluationRun): string {
  const m = r.metrics
  if (!m) return "—"
  if (kindOf(r) === "answers")
    return `abstention ${formatMetric(m.abstention_accuracy)} · citation precision ${formatMetric(m.citation_precision)}`
  return `R@5 ${formatMetric(m.recall_at_5)} · MRR ${formatMetric(m.mrr)} · nDCG@10 ${formatMetric(m.ndcg_at_10)}`
}

type RunChoice = "all_retrieval" | "answers_hybrid_rrf" | keyof typeof RETRIEVAL_LABELS

function RunDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const runEval = useRunEvaluation()
  const [what, setWhat] = useState<RunChoice>("all_retrieval")
  const [split, setSplit] = useState<EvaluationSplit>("test")
  const [limit, setLimit] = useState("")
  const answers = what === "answers_hybrid_rrf"

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const n = Number(limit)
    runEval.mutate(
      {
        config_label: what === "all_retrieval" ? undefined : what,
        split,
        ...(answers && limit && n > 0 ? { limit: Math.floor(n) } : {}),
      },
      {
        onSuccess: () => {
          toast.success(what === "all_retrieval" ? "Queued all four retrieval strategies" : `Started ${configName(what)}`)
          onOpenChange(false)
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Run an evaluation</DialogTitle>
          <DialogDescription>Runs against the versioned synthetic dataset, not your workspace&apos;s documents. Workspace owners only.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="ev-what">What to measure</Label>
            <Select value={what} onValueChange={(v) => setWhat(v as RunChoice)}>
              <SelectTrigger id="ev-what" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all_retrieval">All 4 retrieval strategies (~5–30 s each)</SelectItem>
                {Object.entries(RETRIEVAL_LABELS)
                  .filter(([k]) => k !== "answers_hybrid_rrf")
                  .map(([k, v]) => (
                    <SelectItem key={k} value={k}>
                      {v} only
                    </SelectItem>
                  ))}
                <SelectItem value="answers_hybrid_rrf">Answer quality (~1 min per question)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="ev-split">Question set</Label>
            <Select value={split} onValueChange={(v) => setSplit(v as EvaluationSplit)}>
              <SelectTrigger id="ev-split" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="test">Test (held out — use for reported numbers)</SelectItem>
                <SelectItem value="tune">Tune (for adjusting settings)</SelectItem>
                <SelectItem value="all">All questions</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {answers && (
            <div className="grid gap-1.5">
              <Label htmlFor="ev-limit">Max questions (optional)</Label>
              <Input id="ev-limit" type="number" min={1} max={500} value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="e.g. 10 for a quick check" />
              <p className="text-xs text-muted-foreground">Answers run on the local model, so a full set can take over an hour.</p>
            </div>
          )}
          <DialogFooter>
            <Button type="submit" disabled={runEval.isPending}>
              {runEval.isPending ? <Loader2 className="animate-spin" /> : <Play />} Start
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function EvaluationsPage() {
  const runs = useEvaluationRuns()
  const [dialog, setDialog] = useState(false)
  const [split, setSplit] = useState<EvaluationSplit>("test")
  const all = useMemo(() => runs.data ?? [], [runs.data])
  const cmp = useMemo(() => comparisonSet(all, split), [all, split])
  const answersRun = useMemo(
    () =>
      all
        .filter((r) => kindOf(r) === "answers" && splitOf(r) === split && (r.status === "completed" || r.status === "running"))
        .sort((a, b) => b.started_at.localeCompare(a.started_at))
        .find((r) => r.status === "completed") ??
      all.find((r) => kindOf(r) === "answers" && splitOf(r) === split && r.status === "running"),
    [all, split],
  )

  const config: ChartConfig = Object.fromEntries(cmp.runs.map((r, i) => [`c${i}`, { label: shortName(r.config_label), color: `var(--chart-${(i % 5) + 1})` }]))
  const qualityData = QUALITY.map((m) => ({ metric: m.label, ...Object.fromEntries(cmp.runs.map((r, i) => [`c${i}`, (r.metrics?.[m.key] as number | undefined) ?? null])) }))
  const latencyConfig: ChartConfig = { p50: { label: "p50", color: "var(--chart-1)" }, p95: { label: "p95", color: "var(--chart-3)" } }
  const latencyData = cmp.runs.map((r) => ({ config: shortName(r.config_label), p50: r.metrics?.latency_p50_ms ?? null, p95: r.metrics?.latency_p95_ms ?? null }))
  const kinds = (["lexical", "semantic", "multi"] as const).filter((k) => cmp.runs.some((r) => r.metrics?.by_kind?.[k]))

  const runButton = (
    <Button onClick={() => setDialog(true)}>
      <Play /> Run evaluation
    </Button>
  )

  return (
    <>
      <PageHeader title="Evaluations" description="Measured retrieval and answer quality on a versioned dataset. Only real, completed runs are charted." actions={all.length > 0 && runButton} />
      <RunDialog open={dialog} onOpenChange={setDialog} />
      {runs.isLoading ? (
        <ListSkeleton rows={6} />
      ) : runs.isError ? (
        <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
      ) : all.length === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="No evaluation runs yet"
          description="Run the evaluation suite to compare Lexical, Vector, Hybrid RRF and Hybrid + Rerank. Results appear here once measured."
          action={runButton}
        />
      ) : (
        <div className="space-y-4">
          <Tabs value={split} onValueChange={(v) => setSplit(v as EvaluationSplit)}>
            <TabsList>
              <TabsTrigger value="test">Test set</TabsTrigger>
              <TabsTrigger value="tune">Tune set</TabsTrigger>
              <TabsTrigger value="all">All questions</TabsTrigger>
            </TabsList>
          </Tabs>

          {cmp.version && cmp.runs.length > 0 ? (
            <>
              <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Retrieval quality by strategy</CardTitle>
                    <CardDescription>
                      <Caption run={cmp.runs[0]} at={cmp.latest} split={split} />
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
                      <Caption run={cmp.runs[0]} at={cmp.latest} split={split} />
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <ChartContainer config={latencyConfig} className="aspect-auto h-[280px] w-full">
                      <BarChart data={latencyData} margin={{ left: -8, right: 16 }}>
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

              {kinds.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>By question type</CardTitle>
                    <CardDescription>
                      Lexical questions use exact terms (error codes, names); semantic ones describe symptoms; multi needs more than one section. Recall@5 · MRR.
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Strategy</TableHead>
                          {kinds.map((k) => (
                            <TableHead key={k} className="text-right capitalize">
                              {k} <span className="font-normal text-muted-foreground">(n={cmp.runs.find((r) => r.metrics?.by_kind?.[k])?.metrics?.by_kind?.[k]?.n})</span>
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {cmp.runs.map((r) => (
                          <TableRow key={r.id}>
                            <TableCell className="font-medium">{configName(r.config_label)}</TableCell>
                            {kinds.map((k) => {
                              const b = r.metrics?.by_kind?.[k]
                              return (
                                <TableCell key={k} className="text-right font-mono text-xs tabular-nums">
                                  {b ? `${formatMetric(b.recall_at_5)} · ${formatMetric(b.mrr)}` : "—"}
                                </TableCell>
                              )
                            })}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </>
          ) : (
            <EmptyState icon={BarChart3} title={`No completed retrieval runs on the ${split} set`} description="Charts appear when at least one retrieval run on this question set has finished." />
          )}

          <Card>
            <CardHeader>
              <CardTitle>Answer quality</CardTitle>
              <CardDescription>
                {answersRun ? (
                  <Caption run={answersRun} at={answersRun.finished_at ?? null} split={split} />
                ) : (
                  "Grounded answers from hybrid retrieval and the local model."
                )}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {!answersRun ? (
                <p className="text-sm text-muted-foreground">No answer-quality run on the {split} set yet. Start one with “Run evaluation → Answer quality”.</p>
              ) : answersRun.status === "running" ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Running —{" "}
                  <Link href={`/evaluations/${answersRun.id}`} className="text-primary hover:underline">
                    watch per-question results
                  </Link>
                </p>
              ) : (
                <div className="space-y-3">
                  <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                    {ANSWER_METRICS.map((m) => (
                      <div key={m.key} className="rounded-md border p-3" title={m.hint}>
                        <dt className="text-xs text-muted-foreground">{m.label}</dt>
                        <dd className="mt-0.5 font-mono text-lg tabular-nums">{formatMetric(answersRun.metrics?.[m.key] as number | undefined)}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="font-mono text-[11px] text-muted-foreground">
                    {answersRun.metrics?.questions ?? "?"} questions · {answersRun.metrics?.model_errors ?? 0} model errors · p50 {formatMetric(answersRun.metrics?.latency_p50_ms, "ms")} · p95{" "}
                    {formatMetric(answersRun.metrics?.latency_p95_ms, "ms")} ·{" "}
                    <Link href={`/evaluations/${answersRun.id}`} className="text-primary hover:underline">
                      details
                    </Link>
                  </p>
                  <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                    <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                    Faithfulness isn&apos;t measured yet (no LLM judge). “Expected facts present” is a plain string check, not a judgement of correctness.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>All runs</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Config</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Set</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Result</TableHead>
                    <TableHead className="text-right">p50</TableHead>
                    <TableHead>Started</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {all.map((r) => (
                    <TableRow key={r.id}>
                      <TableCell>
                        <Link href={`/evaluations/${r.id}`} className="font-medium hover:underline">
                          {configName(r.config_label)}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs capitalize">{kindOf(r)}</TableCell>
                      <TableCell className="text-xs">{splitOf(r)}</TableCell>
                      <TableCell>
                        <Pill tone={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "info"} icon={r.status === "running" ? <Loader2 className="size-3 animate-spin" /> : undefined}>
                          {r.status}
                        </Pill>
                      </TableCell>
                      <TableCell className="max-w-[360px] font-mono text-xs">
                        {r.status === "failed" ? <span className="text-destructive">{r.error ?? "failed"}</span> : headline(r)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs tabular-nums">{formatMetric(r.metrics?.latency_p50_ms, "ms")}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap text-muted-foreground">
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
