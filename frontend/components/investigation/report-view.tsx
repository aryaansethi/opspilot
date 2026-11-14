import { AlertTriangle } from "lucide-react"
import { CitationChip } from "@/components/common/citation-chip"
import { absoluteTime } from "@/lib/format"
import type { Report } from "@/lib/types/api"
import { HypothesisCard } from "./hypothesis-card"

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="break-inside-avoid">
      <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  )
}

function Bullets({ items }: { items: string[] }) {
  return items.length ? (
    <ul className="list-disc space-y-1 pl-5 text-sm">
      {items.map((i) => (
        <li key={i}>{i}</li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-muted-foreground">None.</p>
  )
}

export function ReportView({ report, evidenceIndex, onOpenEvidence }: { report: Report; evidenceIndex: Map<string, number | string>; onOpenEvidence: (id: string) => void }) {
  return (
    <div className="space-y-6">
      <Section title="Overview">
        <p className="text-sm leading-relaxed">{report.overview}</p>
        <p className="mt-2 text-xs text-muted-foreground">
          Scope: <span className="font-mono">{report.scope}</span> · v{report.version} · generated {absoluteTime(report.generated_at)}
        </p>
      </Section>

      <Section title="Observed facts">
        <ul className="space-y-2">
          {report.observed_facts.map((f, i) => (
            <li key={i} className="rounded-md border-l-2 border-success/60 bg-muted/30 py-1.5 pr-2 pl-3 text-sm">
              {f.text}
              {f.evidence_ids.map((id) => (
                <CitationChip key={id} n={evidenceIndex.get(id) ?? "?"} onClick={() => onOpenEvidence(id)} />
              ))}
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Hypotheses">
        <div className="space-y-3">
          {report.hypotheses.length ? (
            report.hypotheses.map((h) => <HypothesisCard key={h.id} h={h} evidenceIndex={evidenceIndex} onOpenEvidence={onOpenEvidence} />)
          ) : (
            <p className="text-sm text-muted-foreground">No hypotheses were supported by the evidence.</p>
          )}
        </div>
      </Section>

      <div className="grid gap-6 md:grid-cols-2">
        <Section title="Recommended diagnostics">
          <Bullets items={report.recommended_diagnostics} />
        </Section>
        <Section title="Proposed remediation">
          <Bullets items={report.proposed_remediation} />
        </Section>
      </div>

      <Section title="Unknowns & limitations">
        <div className="flex gap-2 rounded-md border border-warning/30 bg-warning/5 p-3">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
          <div className="min-w-0 flex-1">
            <Bullets items={report.unknowns} />
            {!!report.removed_by_validation?.length && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Removed during validation</p>
              <ul className="space-y-1.5">
                {report.removed_by_validation.map((r, idx) => (
                  <li key={idx} className="rounded-md border border-dashed px-2.5 py-1.5 text-xs">
                    <span className="break-words text-muted-foreground line-through">{r.text}</span>
                    <span className="mt-0.5 block text-[11px] text-muted-foreground">
                      {r.kind === "fact" ? "Fact" : "Hypothesis"} removed — {r.reason}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            )}
          </div>
        </div>
      </Section>

      <Section title="Tool execution summary">
        <p className="text-sm">
          {report.tool_summary.total} tool calls · <span className="text-success">{report.tool_summary.succeeded} succeeded</span> ·{" "}
          <span className={report.tool_summary.failed ? "text-destructive" : "text-muted-foreground"}>{report.tool_summary.failed} failed</span>
        </p>
      </Section>
    </div>
  )
}
