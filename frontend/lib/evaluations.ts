import type { EvaluationMetrics } from "@/lib/types/api"

/** Retrieval strategies the backend knows, in comparison order. */
export const RETRIEVAL_LABELS: Record<string, string> = {
  A_lexical: "Lexical (Postgres FTS)",
  B_vector: "Vector (pgvector)",
  C_hybrid_rrf: "Hybrid RRF",
  D_hybrid_rrf_rerank: "Hybrid RRF + rerank",
  answers_hybrid_rrf: "Answers (hybrid RRF + LLM)",
}
export const configName = (label: string) => RETRIEVAL_LABELS[label] ?? label

/** Compact names for chart axes and legends. */
const SHORT_LABELS: Record<string, string> = {
  A_lexical: "Lexical",
  B_vector: "Vector",
  C_hybrid_rrf: "Hybrid",
  D_hybrid_rrf_rerank: "Hybrid+rerank",
}
export const shortName = (label: string) => SHORT_LABELS[label] ?? configName(label)

export const ANSWER_METRICS: { key: keyof EvaluationMetrics; label: string; hint: string }[] = [
  { key: "abstention_accuracy", label: "Abstention accuracy", hint: "Answered when it should, declined when the knowledge base had no answer" },
  { key: "unanswerable_abstention_rate", label: "Declined unanswerable", hint: "Share of unanswerable questions where it said there wasn't enough evidence" },
  { key: "citation_precision", label: "Citation precision", hint: "Share of citations that point to a relevant section" },
  { key: "citation_coverage", label: "Citation coverage", hint: "Answered questions with at least one relevant citation" },
  { key: "expected_fact_match", label: "Expected facts present", hint: "Answers containing every expected key fact (string match)" },
]
