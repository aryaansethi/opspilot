"use client"

import { Check, ChevronRight, ListChecks, Loader2, X } from "lucide-react"
import { Fragment, use, useMemo, useState } from "react"
import { Pill } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { FilterSelect } from "@/components/common/filter-select"
import { JsonViewer } from "@/components/common/json-viewer"
import { PageHeader } from "@/components/common/page-header"
import { ListSkeleton } from "@/components/common/skeletons"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useEvaluationRun } from "@/lib/api/endpoints/evaluations"
import { configName, metricsFor, runKind } from "@/lib/evaluations"
import { absoluteTime, formatMetric, humanize } from "@/lib/format"
import type { EvaluationMetrics, EvaluationQuestionResult } from "@/lib/types/api"

const RETRIEVAL_METRICS: { key: keyof EvaluationMetrics; label: string }[] = [
  { key: "recall_at_5", label: "Recall@5" },
  { key: "recall_at_10", label: "Recall@10" },
  { key: "precision_at_5", label: "Precision@5" },
  { key: "mrr", label: "MRR" },
  { key: "ndcg_at_5", label: "nDCG@5" },
  { key: "ndcg_at_10", label: "nDCG@10" },
]

type Ref = { document?: string; section?: string }
const refs = (v: unknown): Ref[] => (Array.isArray(v) ? (v as Ref[]) : [])

function RefList({ items, hits }: { items: Ref[]; hits?: boolean[] }) {
  if (!items.length) return <p className="text-xs text-muted-foreground">None</p>
  return (
    <ol className="space-y-1 text-xs">
      {items.map((r, i) => (
        <li key={i} className="flex gap-1.5">
          <span className="w-4 shrink-0 font-mono text-muted-foreground">{i + 1}.</span>
          {hits && (hits[i] ? <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-label="relevant" /> : <X className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-label="not relevant" />)}
          <span>
            <span className="font-mono">{r.document}</span>
            {r.section && <span className="text-muted-foreground"> › {r.section}</span>}
          </span>
        </li>
      ))}
    </ol>
  )
}

function Detail({ q, answers, kind }: { q: EvaluationQuestionResult; answers: boolean; kind: string }) {
  const d = q.detail ?? {}
  if (typeof d.error === "string") return <p className="font-mono text-xs text-destructive">{d.error}</p>
  // Planner and safety cases have their own detail shapes; show them as-is.
  if (kind !== "answers" && kind !== "retrieval") return <JsonViewer value={d} />
  if (answers)
    return (
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Answer{d.insufficient_evidence ? " (declined: insufficient evidence)" : ""}</p>
          <p className="text-sm whitespace-pre-wrap">{String(d.answer ?? "—")}</p>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium text-muted-foreground">Citations</p>
          <RefList items={refs(d.citations)} hits={Array.isArray(d.citation_hits) ? (d.citation_hits as boolean[]) : undefined} />
          {Array.isArray(d.removed_labels) && d.removed_labels.length > 0 && (
            <p className="mt-1 text-xs text-muted-foreground">Invalid citations removed: {(d.removed_labels as string[]).join(", ")}</p>
          )}
        </div>
      </div>
    )
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Expected sections</p>
        <RefList items={refs(d.relevant)} />
      </div>
      <div>
        <p className="mb-1 text-xs font-medium text-muted-foreground">Retrieved (ranked)</p>
        <RefList items={refs(d.retrieved)} />
      </div>
    </div>
  )
}

export default function EvaluationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params)
  const run = useEvaluationRun(runId)
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [kindFilter, setKindFilter] = useState<string>()
  const [outcome, setOutcome] = useState<string>()

  const results = useMemo(() => run.data?.results ?? [], [run.data])
  const isAnswers = run.data ? runKind(run.data) !== "retrieval" : false
  // Retrieval can't "hit" an unanswerable question, so a retrieval miss only counts on answerable ones.
  const shown = useMemo(
    () =>
      results.filter(
        (q) =>
          (!kindFilter || q.kind === kindFilter) &&
          (!outcome || (outcome === "miss" ? !q.hit_at_5 && (isAnswers || q.answerable) : q.hit_at_5)),
      ),
    [results, kindFilter, outcome, isAnswers],
  )

  if (run.isLoading) return <ListSkeleton rows={6} />
  if (run.isError) return <ErrorState error={run.error} onRetry={() => run.refetch()} />
  const r = run.data!
  const kind = runKind(r)
  const answers = kind === "answers"
  const scored = kind !== "retrieval" // per-case pass/fail rather than ranking
  const m = r.metrics ?? {}
  const tiles = kind === "retrieval" ? RETRIEVAL_METRICS : metricsFor(kind).filter((t) => t.key !== "faithfulness" || m.faithfulness != null)
  const byKind = Object.entries(m.by_kind ?? {})
  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <>
      <PageHeader
        title={configName(r.config_label)}
        description={
          <span className="font-mono text-xs">
            {r.config_label} · {r.dataset_name}@{r.dataset_version}
            {r.dataset_hash ? ` (${r.dataset_hash.slice(0, 8)})` : ""} · {r.split ?? "test"} set · started {absoluteTime(r.started_at)}
            {r.finished_at ? ` · finished ${absoluteTime(r.finished_at)}` : ""}
          </span>
        }
        actions={
          <Pill tone={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "info"} icon={r.status === "running" ? <Loader2 className="size-3 animate-spin" /> : undefined}>
            {r.status}
          </Pill>
        }
      />
      {r.status === "failed" && r.error && (
        <div role="alert" className="mb-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 font-mono text-xs text-destructive">
          {r.error}
        </div>
      )}
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {!r.metrics ? (
              <p className="text-sm text-muted-foreground">
                {r.status === "running" ? `Running — ${results.length} question${results.length === 1 ? "" : "s"} done so far. Metrics appear when the run finishes.` : "No metrics recorded for this run."}
              </p>
            ) : (
              <>
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {tiles.map((t) => (
                    <div key={t.key} className="rounded-md border p-3">
                      <dt className="text-xs text-muted-foreground">{t.label}</dt>
                      <dd className="mt-0.5 font-mono text-lg tabular-nums">{formatMetric(m[t.key] as number | undefined)}</dd>
                    </div>
                  ))}
                  {(["latency_p50_ms", "latency_p95_ms"] as const).map((k) => (
                    <div key={k} className="rounded-md border p-3">
                      <dt className="text-xs text-muted-foreground">Latency {k === "latency_p50_ms" ? "p50" : "p95"}</dt>
                      <dd className="mt-0.5 font-mono text-lg tabular-nums">{formatMetric(m[k], "ms")}</dd>
                    </div>
                  ))}
                </dl>
                <p className="font-mono text-[11px] text-muted-foreground">
                  {m.questions ?? "?"} questions
                  {m.answerable_questions !== undefined && ` · ${m.answerable_questions} answerable`}
                  {m.model_errors !== undefined && ` · ${m.model_errors} model errors`}
                  {m.cases !== undefined && ` · ${m.cases} cases`}
                  {answers && (m.faithfulness != null ? ` · faithfulness judged by ${m.faithfulness_judge ?? "an LLM"} over ${m.claims_judged ?? "?"} claims` : " · faithfulness not measured")}
                </p>
                {byKind.length > 0 && (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Question type</TableHead>
                        <TableHead className="text-right">n</TableHead>
                        <TableHead className="text-right">Recall@5</TableHead>
                        <TableHead className="text-right">MRR</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {byKind.map(([k, b]) => (
                        <TableRow key={k}>
                          <TableCell className="capitalize">{k}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{b?.n}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{formatMetric(b?.recall_at_5)}</TableCell>
                          <TableCell className="text-right font-mono text-xs">{formatMetric(b?.mrr)}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Configuration</CardTitle>
          </CardHeader>
          <CardContent>
            <JsonViewer value={r.config} />
          </CardContent>
        </Card>
      </div>
      <Card className="mt-4">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
          <CardTitle>
            Per-question results <span className="font-normal text-muted-foreground">({shown.length})</span>
          </CardTitle>
          <div className="flex flex-wrap gap-2">
            <FilterSelect
              value={kindFilter}
              onChange={setKindFilter}
              label="Question type"
              allLabel="All types"
              options={[...new Set(results.map((q) => q.kind).filter((k): k is string => !!k))].sort().map((k) => ({ value: k, label: humanize(k) }))}
            />
            <FilterSelect
              value={outcome}
              onChange={setOutcome}
              label="Outcome"
              allLabel="Hits and misses"
              options={[
                { value: "miss", label: scored ? "Wrong only" : "Misses only" },
                { value: "hit", label: scored ? "Correct only" : "Hits only" },
              ]}
            />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {shown.length === 0 ? (
            <EmptyState icon={ListChecks} title={results.length ? "No questions match these filters" : "No per-question results yet"} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>ID</TableHead>
                  <TableHead>Question</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-center">{scored ? "Correct" : "Hit@5"}</TableHead>
                  {!scored && <TableHead className="text-right">RR</TableHead>}
                  <TableHead className="text-right">Latency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shown.map((q) => {
                  const isOpen = open.has(q.question_id)
                  return (
                    <Fragment key={q.question_id}>
                      <TableRow className="cursor-pointer" onClick={() => toggle(q.question_id)} aria-expanded={isOpen}>
                        <TableCell>
                          <ChevronRight className={`size-4 text-muted-foreground transition-transform ${isOpen ? "rotate-90" : ""}`} aria-hidden />
                        </TableCell>
                        <TableCell className="font-mono text-xs">{q.question_id}</TableCell>
                        <TableCell className="max-w-[420px] truncate">{q.question}</TableCell>
                        <TableCell>{q.kind === "unanswerable" ? <Pill tone="warning">unanswerable</Pill> : <Pill>{q.kind ?? (q.answerable ? "answerable" : "unanswerable")}</Pill>}</TableCell>
                        <TableCell className="text-center">
                          {q.hit_at_5 ? <Check className="mx-auto size-4 text-success" aria-label="yes" /> : <X className="mx-auto size-4 text-muted-foreground" aria-label="no" />}
                        </TableCell>
                        {!scored && <TableCell className="text-right font-mono text-xs">{q.reciprocal_rank.toFixed(3)}</TableCell>}
                        <TableCell className="text-right font-mono text-xs whitespace-nowrap">{formatMetric(q.latency_ms, "ms")}</TableCell>
                      </TableRow>
                      {isOpen && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell />
                          <TableCell colSpan={scored ? 5 : 6} className="bg-muted/30 whitespace-normal">
                            <Detail q={q} answers={answers} kind={kind} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}
