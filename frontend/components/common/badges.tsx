import { BookOpen, Cloud, GitBranch, Loader2, SquareKanban } from "lucide-react"
import type { ReactNode } from "react"
import { humanize } from "@/lib/format"
import type { DocStatus, InvestigationState, SourceSystem, SourceType } from "@/lib/types/api"
import { cn } from "@/lib/utils"

export type Tone = "neutral" | "success" | "warning" | "danger" | "info" | "accent"

const toneClass: Record<Tone, string> = {
  neutral: "border-border bg-muted/60 text-muted-foreground",
  success: "border-success/30 bg-success/10 text-success",
  warning: "border-warning/30 bg-warning/10 text-warning",
  danger: "border-destructive/30 bg-destructive/10 text-destructive",
  info: "border-info/30 bg-info/10 text-info",
  accent: "border-primary/30 bg-primary/10 text-primary",
}

export function Pill({ tone = "neutral", children, className, icon }: { tone?: Tone; children: ReactNode; className?: string; icon?: ReactNode }) {
  return (
    <span className={cn("inline-flex h-5 shrink-0 items-center gap-1 rounded-md border px-1.5 text-[11px] font-medium whitespace-nowrap", toneClass[tone], className)}>
      {icon}
      {children}
    </span>
  )
}

const spinner = <Loader2 className="size-3 animate-spin" aria-hidden />

export function DocStatusBadge({ status }: { status: DocStatus }) {
  const map: Record<DocStatus, [Tone, string]> = {
    pending_upload: ["neutral", "Uploading"],
    queued: ["info", "Queued"],
    processing: ["info", "Processing"],
    indexed: ["success", "Indexed"],
    failed: ["danger", "Failed"],
  }
  const [tone, label] = map[status]
  return (
    <Pill tone={tone} icon={status === "queued" || status === "processing" ? spinner : undefined}>
      {label}
    </Pill>
  )
}

export const TERMINAL_STATES: InvestigationState[] = ["COMPLETED", "PARTIAL", "FAILED_INVALID_PARAMS", "FAILED_LLM", "FAILED_RETRIEVAL"]

export function isRunning(state: InvestigationState) {
  return !TERMINAL_STATES.includes(state) && state !== "AWAITING_PARAMETERS" && state !== "AWAITING_ACTION"
}

export function InvestigationStateBadge({ state }: { state: InvestigationState }) {
  let tone: Tone = "info"
  let label = humanize(state)
  if (state === "COMPLETED") tone = "success"
  else if (state === "PARTIAL") [tone, label] = ["warning", "Partial"]
  else if (state.startsWith("FAILED")) [tone, label] = ["danger", `Failed · ${humanize(state.replace("FAILED_", ""))}`]
  else if (state === "AWAITING_PARAMETERS") [tone, label] = ["warning", "Needs input"]
  else if (state === "AWAITING_ACTION") [tone, label] = ["accent", "Report ready"]
  return (
    <Pill tone={tone} icon={isRunning(state) ? spinner : undefined}>
      {isRunning(state) ? "Running · " : ""}
      {label}
    </Pill>
  )
}

export const sourceMeta: Record<SourceSystem, { label: string; live: boolean; icon: typeof Cloud }> = {
  knowledge_base: { label: "Knowledge base", live: false, icon: BookOpen },
  github: { label: "GitHub", live: true, icon: GitBranch },
  cloudwatch: { label: "CloudWatch", live: true, icon: Cloud },
  jira: { label: "Jira", live: true, icon: SquareKanban },
}

export function SourceBadge({ source }: { source: SourceSystem }) {
  const m = sourceMeta[source]
  const Icon = m.icon
  return (
    <Pill tone={m.live ? "accent" : "info"} icon={<Icon className="size-3" aria-hidden />}>
      {m.live ? `Live · ${m.label}` : m.label}
    </Pill>
  )
}

export function SourceTypeBadge({ type }: { type: SourceType }) {
  const labels: Record<SourceType, string> = {
    runbook: "Runbook",
    architecture: "Architecture",
    incident_report: "Incident report",
    other: "Other",
  }
  return <Pill>{labels[type]}</Pill>
}

export function AccessBadge({ access }: { access: "read" | "write" }) {
  return access === "write" ? <Pill tone="warning">WRITE</Pill> : <Pill>READ</Pill>
}
