import { cn } from "@/lib/utils"
import type { StageTimings as Timings } from "@/lib/types/api"

const LABELS: Record<string, string> = {
  // search
  lexical: "full-text",
  embed_query: "embed",
  vector: "vector",
  fusion: "fusion",
  rerank: "rerank",
  // ask
  retrieval: "retrieval",
  generation: "generation",
  // investigation
  plan_llm: "plan (LLM)",
  knowledge_retrieval: "knowledge base",
  read_tools: "tools",
  analysis_llm: "analysis (LLM)",
  report: "report",
}

export function formatDuration(ms: number): string {
  if (ms < 1) return "<1 ms"
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`
}

/**
 * Per-stage latency as a compact line ("full-text 5 ms · vector 130 ms · … · total 142 ms").
 * Stages are shown in the order given, then any unknown ones; `total` is always last.
 */
export function StageTimings({ timings, order, className }: { timings?: Timings | null; order: string[]; className?: string }) {
  if (!timings) return null
  const entries = Object.entries(timings).filter((e): e is [string, number] => typeof e[1] === "number")
  if (!entries.length) return null
  const rank = (k: string) => (k === "total" ? 1e9 : order.indexOf(k) === -1 ? 1e6 : order.indexOf(k))
  entries.sort((a, b) => rank(a[0]) - rank(b[0]))
  return (
    <p className={cn("font-mono text-[11px] text-muted-foreground", className)} aria-label="Latency by stage">
      {entries.map(([k, v], i) => (
        <span key={k}>
          {i > 0 && " · "}
          <span className={k === "total" ? "text-foreground" : undefined}>
            {k === "total" ? "total" : (LABELS[k] ?? k.replace(/_/g, " "))} {formatDuration(v)}
          </span>
        </span>
      ))}
    </p>
  )
}
