import { ExternalLink } from "lucide-react"
import { SourceBadge } from "@/components/common/badges"
import { RelativeTime } from "@/components/common/relative-time"
import { shortTime } from "@/lib/format"
import type { Evidence } from "@/lib/types/api"
import { cn } from "@/lib/utils"

export function EvidenceCard({ evidence, index, highlighted, className }: { evidence: Evidence; index?: number | string; highlighted?: boolean; className?: string }) {
  const e = evidence
  return (
    <article id={`evidence-${e.id}`} className={cn("rounded-lg border bg-card p-3.5 transition-colors", highlighted && "border-primary ring-1 ring-primary/40", className)}>
      <div className="flex flex-wrap items-center gap-2">
        {index != null && <span className="font-mono text-[11px] text-muted-foreground">[{index}]</span>}
        <SourceBadge source={e.source_system} />
        <span className="ml-auto text-xs text-muted-foreground">
          {e.observed_at ? <RelativeTime iso={e.observed_at} /> : null}
        </span>
      </div>
      <h4 className="mt-2 text-sm font-medium">{e.title}</h4>
      <p className={cn("mt-1 text-sm text-muted-foreground", e.source_system !== "knowledge_base" && "font-mono text-xs leading-relaxed")}>{e.excerpt}</p>
      {e.time_range && (
        <p className="mt-1.5 font-mono text-[11px] text-muted-foreground">
          {shortTime(e.time_range.start)} → {shortTime(e.time_range.end)}
        </p>
      )}
      {e.reliability_notes && <p className="mt-1.5 text-xs text-warning">{e.reliability_notes}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
        <span className="truncate font-mono">{e.source_reference}</span>
        {e.retrieval_method && (
          <span>
            via <span className="font-mono">{e.retrieval_method}</span>
            {e.rank != null && ` · rank ${e.rank}`}
          </span>
        )}
        {e.url && (
          <a href={e.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
            Open source <ExternalLink className="size-3" />
          </a>
        )}
      </div>
    </article>
  )
}
