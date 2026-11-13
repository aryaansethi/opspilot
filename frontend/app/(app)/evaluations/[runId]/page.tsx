"use client"

import { Check, ListChecks, X } from "lucide-react"
import { use } from "react"
import { Pill } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { JsonViewer } from "@/components/common/json-viewer"
import { PageHeader } from "@/components/common/page-header"
import { ListSkeleton } from "@/components/common/skeletons"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useEvaluationRun } from "@/lib/api/endpoints/evaluations"
import { absoluteTime, formatMetric } from "@/lib/format"
import type { EvaluationMetrics } from "@/lib/types/api"

const LABELS: Partial<Record<keyof EvaluationMetrics, string>> = {
  recall_at_5: "Recall@5",
  recall_at_10: "Recall@10",
  precision_at_5: "Precision@5",
  mrr: "MRR",
  ndcg_at_5: "nDCG@5",
  ndcg_at_10: "nDCG@10",
  faithfulness: "Faithfulness",
  citation_precision: "Citation precision",
  abstention_accuracy: "Abstention accuracy",
  tool_success_rate: "Tool success rate",
  latency_p50_ms: "Latency p50",
  latency_p95_ms: "Latency p95",
}

export default function EvaluationRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params)
  const run = useEvaluationRun(runId)

  if (run.isLoading) return <ListSkeleton rows={6} />
  if (run.isError) return <ErrorState error={run.error} onRetry={() => run.refetch()} />
  const r = run.data!
  const metrics = Object.entries(r.metrics ?? {}) as [keyof EvaluationMetrics, number][]

  return (
    <>
      <PageHeader
        title={r.config_label}
        description={
          <span className="font-mono text-xs">
            {r.dataset_name}@{r.dataset_version} · started {absoluteTime(r.started_at)}
            {r.finished_at ? ` · finished ${absoluteTime(r.finished_at)}` : ""}
          </span>
        }
        actions={<Pill tone={r.status === "completed" ? "success" : r.status === "failed" ? "danger" : "info"}>{r.status}</Pill>}
      />
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader>
            <CardTitle>Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            {metrics.length === 0 ? (
              <p className="text-sm text-muted-foreground">No metrics recorded {r.status === "running" ? "yet" : "for this run"}.</p>
            ) : (
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {metrics.map(([k, v]) => (
                  <div key={k} className="rounded-md border p-3">
                    <dt className="text-xs text-muted-foreground">{LABELS[k] ?? k}</dt>
                    <dd className="mt-0.5 font-mono text-lg tabular-nums">{formatMetric(v, k.endsWith("_ms") ? "ms" : "ratio")}</dd>
                  </div>
                ))}
              </dl>
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
        <CardHeader>
          <CardTitle>Per-question results</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {r.results.length === 0 ? (
            <EmptyState icon={ListChecks} title="No per-question results" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Question</TableHead>
                  <TableHead>Answerable</TableHead>
                  <TableHead className="text-center">Hit@5</TableHead>
                  <TableHead className="text-right">RR</TableHead>
                  <TableHead className="text-right">Latency</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {r.results.map((q) => (
                  <TableRow key={q.question_id}>
                    <TableCell className="max-w-[420px] truncate">{q.question}</TableCell>
                    <TableCell>{q.answerable ? <Pill>yes</Pill> : <Pill tone="warning">no</Pill>}</TableCell>
                    <TableCell className="text-center">
                      {q.hit_at_5 ? <Check className="mx-auto size-4 text-success" aria-label="hit" /> : <X className="mx-auto size-4 text-muted-foreground" aria-label="miss" />}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{q.reciprocal_rank.toFixed(3)}</TableCell>
                    <TableCell className="text-right font-mono text-xs">{q.latency_ms} ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </>
  )
}
