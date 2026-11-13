import { Lightbulb } from "lucide-react"
import { Pill, type Tone } from "@/components/common/badges"
import { CitationChip } from "@/components/common/citation-chip"
import { Checkbox } from "@/components/ui/checkbox"
import type { Hypothesis } from "@/lib/types/api"

const statusTone: Record<Hypothesis["status"], Tone> = { proposed: "neutral", supported: "info", refuted: "danger", confirmed: "success" }

/** "Root cause" is reserved for hypotheses the backend has marked confirmed. */
export function guardRootCause(text: string, status: Hypothesis["status"]) {
  return status === "confirmed" ? text : text.replace(/\broot[- ]cause\b/gi, "possible cause")
}

export function HypothesisCard({ h, evidenceIndex, onOpenEvidence }: { h: Hypothesis; evidenceIndex: Map<string, number>; onOpenEvidence: (id: string) => void }) {
  return (
    <article className="rounded-lg border border-dashed border-primary/40 bg-primary/[0.03] p-4">
      <div className="mb-2 flex items-center gap-2">
        <Lightbulb className="size-3.5 text-primary" aria-hidden />
        <span className="text-[11px] font-semibold tracking-wide text-primary uppercase">{h.status === "confirmed" ? "Confirmed root cause" : "Hypothesis"}</span>
        <Pill tone={statusTone[h.status]} className="ml-auto capitalize">
          {h.status}
        </Pill>
      </div>
      <p className="text-sm font-medium">{guardRootCause(h.statement, h.status)}</p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">Supporting evidence</p>
          {h.supporting_evidence_ids.length ? (
            <div className="flex flex-wrap gap-1">
              {h.supporting_evidence_ids.map((id) => (
                <CitationChip key={id} n={evidenceIndex.get(id) ?? "?"} tone="support" onClick={() => onOpenEvidence(id)} label={`Open supporting evidence ${evidenceIndex.get(id) ?? ""}`} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">None</p>
          )}
        </div>
        <div>
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">Contradicting evidence</p>
          {h.contradicting_evidence_ids.length ? (
            <div className="flex flex-wrap gap-1">
              {h.contradicting_evidence_ids.map((id) => (
                <CitationChip key={id} n={evidenceIndex.get(id) ?? "?"} tone="contradict" onClick={() => onOpenEvidence(id)} label={`Open contradicting evidence ${evidenceIndex.get(id) ?? ""}`} />
              ))}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">None found</p>
          )}
        </div>
      </div>

      <div className="mt-3">
        <p className="mb-1 text-[11px] font-medium text-muted-foreground">Why this confidence</p>
        <p className="text-sm text-muted-foreground">{h.confidence_explanation}</p>
      </div>

      {h.missing_evidence.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">Missing evidence</p>
          <ul className="list-disc space-y-0.5 pl-4 text-sm text-muted-foreground">
            {h.missing_evidence.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}

      {h.validation_steps.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[11px] font-medium text-muted-foreground">How to validate</p>
          <ul className="space-y-1">
            {h.validation_steps.map((s) => (
              <li key={s}>
                <label className="flex items-start gap-2 text-sm">
                  <Checkbox className="mt-0.5" />
                  <span>{s}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}
