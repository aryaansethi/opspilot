import type { EvaluationMetrics } from "@/lib/types/api"

/** Retrieval strategies the backend knows, in comparison order. */
export const RETRIEVAL_LABELS: Record<string, string> = {
  A_lexical: "Lexical (Postgres FTS)",
  B_vector: "Vector (pgvector)",
  C_hybrid_rrf: "Hybrid RRF",
  D_hybrid_rrf_rerank: "Hybrid RRF + rerank",
  E_hybrid_weighted: "Hybrid, tuned weights",
  F_hybrid_weighted_rerank: "Hybrid, tuned + rerank",
  answers_hybrid_rrf: "Answers (hybrid RRF + LLM)",
  tool_selection_planner: "Tool selection (planner)",
  injection_resistance: "Prompt-injection resistance",
}

/** Configs that produce retrieval metrics (everything else is an answers / planner / safety run). */
export const isRetrievalLabel = (label: string) => /^[A-Z]_/.test(label)
export const configName = (label: string) => RETRIEVAL_LABELS[label] ?? label

/** Compact names for chart axes and legends. */
const SHORT_LABELS: Record<string, string> = {
  A_lexical: "Lexical",
  B_vector: "Vector",
  C_hybrid_rrf: "Hybrid",
  D_hybrid_rrf_rerank: "Hybrid+rerank",
  E_hybrid_weighted: "Tuned hybrid",
  F_hybrid_weighted_rerank: "Tuned+rerank",
}
export const shortName = (label: string) => SHORT_LABELS[label] ?? configName(label)

export type MetricDef = { key: keyof EvaluationMetrics; label: string; hint: string }

export const ANSWER_METRICS: MetricDef[] = [
  { key: "faithfulness", label: "Faithfulness", hint: "Share of answer claims an LLM judge found supported by the cited context" },
  { key: "abstention_accuracy", label: "Abstention accuracy", hint: "Answered when it should, declined when the knowledge base had no answer" },
  { key: "unanswerable_abstention_rate", label: "Declined unanswerable", hint: "Share of unanswerable questions where it said there wasn't enough evidence" },
  { key: "citation_precision", label: "Citation precision", hint: "Share of citations that point to a relevant section" },
  { key: "citation_coverage", label: "Citation coverage", hint: "Answered questions with at least one relevant citation" },
  { key: "expected_fact_match", label: "Expected facts present", hint: "Answers containing every expected key fact (string match)" },
]

export const TOOL_SELECTION_METRICS: MetricDef[] = [
  { key: "tool_selection_accuracy", label: "Exact-set accuracy", hint: "Cases where the planner chose exactly the expected tasks" },
  { key: "tool_selection_precision", label: "Precision", hint: "Share of chosen tasks that were expected" },
  { key: "tool_selection_recall", label: "Recall", hint: "Share of expected tasks the planner chose" },
]

export const INJECTION_METRICS: MetricDef[] = [
  { key: "injection_resistance", label: "Injection resistance", hint: "Cases where instructions planted in documents or tool output were not followed" },
]

/** Metric definitions for a run, by kind. */
export function metricsFor(kind: string | undefined): MetricDef[] {
  if (kind === "answers") return ANSWER_METRICS
  if (kind === "tool_selection") return TOOL_SELECTION_METRICS
  if (kind === "injection") return INJECTION_METRICS
  return []
}

/** Run kind, inferring it for older runs that predate the `kind` field. */
export function runKind(r: { kind?: string; config_label: string }): string {
  if (r.kind) return r.kind
  if (r.config_label.startsWith("answers")) return "answers"
  if (r.config_label.startsWith("tool_selection")) return "tool_selection"
  if (r.config_label.startsWith("injection")) return "injection"
  return "retrieval"
}
