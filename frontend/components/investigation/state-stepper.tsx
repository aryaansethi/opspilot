import { AlertTriangle, Check, Circle, Loader2, PauseCircle, X } from "lucide-react"
import { humanize } from "@/lib/format"
import type { InvestigationEvent, InvestigationState } from "@/lib/types/api"
import { cn } from "@/lib/utils"

export const PIPELINE: { state: InvestigationState; label: string }[] = [
  { state: "CLASSIFY_REQUEST", label: "Classify request" },
  { state: "COLLECT_PARAMETERS", label: "Collect parameters" },
  { state: "PLAN_INVESTIGATION", label: "Plan investigation" },
  { state: "RUN_KNOWLEDGE_RETRIEVAL", label: "Search knowledge base" },
  { state: "RUN_READ_TOOLS", label: "Run read-only tools" },
  { state: "NORMALIZE_EVIDENCE", label: "Normalize evidence" },
  { state: "ANALYZE_HYPOTHESES", label: "Form hypotheses" },
  { state: "CHECK_CITATIONS", label: "Check citations" },
  { state: "GENERATE_REPORT", label: "Generate report" },
]

type StepStatus = "done" | "current" | "waiting" | "failed" | "warning" | "pending"

export function computeSteps(state: InvestigationState, events: InvestigationEvent[], failedSteps: string[] = []): StepStatus[] {
  const reached = events.filter((e) => e.type === "state_changed").map((e) => (e.payload.to ?? e.payload.state) as InvestigationState)
  const lastPipelineIdx = Math.max(-1, ...reached.map((s) => PIPELINE.findIndex((p) => p.state === s)))
  const toolsIdx = PIPELINE.findIndex((p) => p.state === "RUN_READ_TOOLS")

  if (state === "AWAITING_ACTION" || state === "COMPLETED") return PIPELINE.map(() => "done")
  if (state === "PARTIAL") return PIPELINE.map((_, i) => (i === toolsIdx && failedSteps.length ? "warning" : "done"))
  if (state === "AWAITING_PARAMETERS") {
    const idx = PIPELINE.findIndex((p) => p.state === "COLLECT_PARAMETERS")
    return PIPELINE.map((_, i) => (i < idx ? "done" : i === idx ? "waiting" : "pending"))
  }
  if (state.startsWith("FAILED")) {
    const idx = Math.max(0, lastPipelineIdx)
    return PIPELINE.map((_, i) => (i < idx ? "done" : i === idx ? "failed" : "pending"))
  }
  const cur = PIPELINE.findIndex((p) => p.state === state)
  const idx = cur === -1 ? Math.max(-1, lastPipelineIdx) : cur
  return PIPELINE.map((_, i) => (i < idx ? "done" : i === idx ? "current" : "pending"))
}

const icon: Record<StepStatus, React.ReactNode> = {
  done: <Check className="size-3" />,
  current: <Loader2 className="size-3 animate-spin" />,
  waiting: <PauseCircle className="size-3" />,
  failed: <X className="size-3" />,
  warning: <AlertTriangle className="size-3" />,
  pending: <Circle className="size-2" />,
}

const tone: Record<StepStatus, string> = {
  done: "border-success/40 bg-success/15 text-success",
  current: "border-primary bg-primary/15 text-primary",
  waiting: "border-warning/50 bg-warning/15 text-warning",
  failed: "border-destructive/50 bg-destructive/15 text-destructive",
  warning: "border-warning/50 bg-warning/15 text-warning",
  pending: "border-border bg-muted text-muted-foreground",
}

export function StateStepper({ state, events, failedSteps }: { state: InvestigationState; events: InvestigationEvent[]; failedSteps?: string[] }) {
  const steps = computeSteps(state, events, failedSteps)
  return (
    <ol className="space-y-0" aria-label="Investigation progress">
      {PIPELINE.map((p, i) => {
        const s = steps[i]
        return (
          <li key={p.state} className="relative flex items-center gap-3 py-1.5" aria-current={s === "current" || s === "waiting" ? "step" : undefined}>
            {i < PIPELINE.length - 1 && <span className={cn("absolute top-6 left-[9px] h-[calc(100%-12px)] w-px", s === "done" ? "bg-success/40" : "bg-border")} aria-hidden />}
            <span className={cn("relative z-10 flex size-[19px] shrink-0 items-center justify-center rounded-full border", tone[s], s === "current" && "animate-pulse")}>{icon[s]}</span>
            <span className={cn("text-sm", s === "pending" ? "text-muted-foreground" : "text-foreground", (s === "current" || s === "waiting") && "font-medium")}>
              {p.label}
              <span className="sr-only"> — {humanize(s)}</span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}
