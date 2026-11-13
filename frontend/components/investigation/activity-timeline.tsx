import { AlertCircle, CheckCircle2, FileText, Lightbulb, PauseCircle, ShieldAlert, Sparkles } from "lucide-react"
import { sourceMeta } from "@/components/common/badges"
import { format } from "date-fns"
import { humanize } from "@/lib/format"
import type { InvestigationEvent, SourceSystem, ToolCall } from "@/lib/types/api"
import { ToolCallItem } from "./tool-call-item"

function Line({ icon: Icon, children, at, tone = "text-muted-foreground" }: { icon: typeof FileText; children: React.ReactNode; at: string; tone?: string }) {
  return (
    <li className="flex items-start gap-2 py-1 text-xs">
      <Icon className={`mt-0.5 size-3.5 shrink-0 ${tone}`} aria-hidden />
      <span className="flex-1">{children}</span>
      <time className="font-mono text-[10px] text-muted-foreground" dateTime={at}>
        {format(new Date(at), "HH:mm:ss")}
      </time>
    </li>
  )
}

export function ActivityTimeline({ events, toolCalls }: { events: InvestigationEvent[]; toolCalls: ToolCall[] }) {
  const byId = new Map(toolCalls.map((t) => [t.id, t]))
  const seenTools = new Set<string>()
  const items: React.ReactNode[] = []

  // The backend's started event has no id, so pair each start with the next completion of the same tool;
  // a start that already has its completion is hidden (the completed row replaces it).
  const finishedStarts = new Set<number>()
  const openStarts = new Map<string, number[]>()
  for (const e of events) {
    const tool = String(e.payload.tool ?? "")
    if (e.type === "tool_call_started") openStarts.set(tool, [...(openStarts.get(tool) ?? []), e.seq])
    else if (e.type === "tool_call_completed") {
      const q = openStarts.get(tool)
      const seq = q?.shift()
      if (seq !== undefined) finishedStarts.add(seq)
    }
  }

  for (const e of events) {
    const key = `${e.seq}`
    switch (e.type) {
      case "state_changed":
        items.push(
          <Line key={key} icon={Sparkles} at={e.at}>
            Stage → <span className="text-foreground">{humanize(String(e.payload.to ?? e.payload.state))}</span>
          </Line>,
        )
        break
      case "tool_call_started":
      case "tool_call_completed": {
        // Real backend: only the completed event carries the invocation id. Mock: both carry tool_call_id.
        const rawId = e.payload.invocation_id ?? e.payload.tool_call_id
        const call = rawId ? byId.get(String(rawId)) : undefined
        if (call) {
          if (seenTools.has(call.id)) break
          seenTools.add(call.id)
          items.push(
            <li key={key} className="py-1">
              <ToolCallItem call={call} />
            </li>,
          )
        } else if (e.type === "tool_call_started" && !finishedStarts.has(e.seq)) {
          items.push(
            <Line key={key} icon={Sparkles} at={e.at}>
              Calling <span className="font-mono text-foreground">{String(e.payload.tool ?? e.payload.name ?? "tool")}</span>…
            </Line>,
          )
        }
        break
      }
      case "evidence_added": {
        const src = e.payload.source_system as SourceSystem | undefined
        items.push(
          <Line key={key} icon={FileText} at={e.at}>
            Evidence added from {src && sourceMeta[src] ? sourceMeta[src].label : "a source"}
          </Line>,
        )
        break
      }
      case "hypothesis_added":
        items.push(
          <Line key={key} icon={Lightbulb} at={e.at}>
            Hypothesis proposed
          </Line>,
        )
        break
      case "report_ready":
        items.push(
          <Line key={key} icon={CheckCircle2} at={e.at} tone="text-success">
            Report ready
          </Line>,
        )
        break
      case "approval_requested":
        items.push(
          <Line key={key} icon={ShieldAlert} at={e.at} tone="text-warning">
            Write action awaiting approval
          </Line>,
        )
        break
      case "parameters_required":
        items.push(
          <Line key={key} icon={PauseCircle} at={e.at} tone="text-warning">
            Waiting for: {(e.payload.missing as string[] | undefined)?.map(humanize).join(", ") ?? "more details"}
          </Line>,
        )
        break
      case "step_failed":
      case "error":
        items.push(
          <Line key={key} icon={AlertCircle} at={e.at} tone="text-destructive">
            {String(e.payload.message ?? e.payload.step ?? "Step failed")}
          </Line>,
        )
        break
      default:
        break
    }
  }

  // Tool calls that arrived without a matching event (e.g. loaded from history).
  for (const t of toolCalls) {
    if (!seenTools.has(t.id))
      items.push(
        <li key={t.id} className="py-1">
          <ToolCallItem call={t} />
        </li>,
      )
  }

  if (!items.length) return <p className="py-4 text-center text-xs text-muted-foreground">Waiting for activity…</p>
  return (
    <ol className="space-y-0.5" aria-live="polite">
      {items}
    </ol>
  )
}
