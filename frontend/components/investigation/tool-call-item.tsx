"use client"

import { ChevronRight, Cloud, GitBranch, Loader2, SquareKanban, Wrench } from "lucide-react"
import { useState } from "react"
import { AccessBadge, Pill, type Tone } from "@/components/common/badges"
import { JsonViewer } from "@/components/common/json-viewer"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { formatBytes } from "@/lib/format"
import type { ToolCall } from "@/lib/types/api"
import { cn } from "@/lib/utils"

const serverIcon: Record<string, typeof Cloud> = { github: GitBranch, cloudwatch: Cloud, jira: SquareKanban }
const statusTone: Record<ToolCall["status"], Tone> = { running: "info", succeeded: "success", failed: "danger", timeout: "warning", denied: "danger" }

export function ToolCallItem({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false)
  const Icon = serverIcon[call.server] ?? Wrench
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-md border bg-card">
      <CollapsibleTrigger className="flex w-full items-center gap-2 px-2.5 py-2 text-left focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
        <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} aria-hidden />
        <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          <span className="text-muted-foreground">{call.server}.</span>
          {call.tool}
        </span>
        <Pill tone={statusTone[call.status]} icon={call.status === "running" ? <Loader2 className="size-3 animate-spin" /> : undefined}>
          {call.status}
        </Pill>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 border-t px-2.5 py-2">
        <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <AccessBadge access={call.access} />
          {call.duration_ms !== undefined && <span>{call.duration_ms} ms</span>}
          {call.result_bytes !== undefined && <span>{formatBytes(call.result_bytes)} returned</span>}
        </div>
        <p className="text-[11px] text-muted-foreground">Arguments (redacted)</p>
        <JsonViewer value={call.arguments_redacted} />
        {call.error && <p className="text-xs text-destructive">{call.error}</p>}
      </CollapsibleContent>
    </Collapsible>
  )
}
