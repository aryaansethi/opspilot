"""Assemble the structured report and its Markdown rendering."""

from datetime import UTC, datetime
from typing import Any

from app.investigations.analysis import ValidatedAnalysis
from app.models import EvidenceItem, Investigation


def scope_text(inv: Investigation, sources: list[str]) -> str:
    window = (
        f"{inv.time_start.isoformat()} to {inv.time_end.isoformat()}"
        if inv.time_start and inv.time_end
        else "not set"
    )
    return (
        f"Service {inv.service or 'unspecified'} in {inv.environment or 'unspecified environment'}; "
        f"time window {window}; sources consulted: {', '.join(sources) or 'none'}."
    )


def build_report(
    inv: Investigation,
    scope: str,
    analysis: ValidatedAnalysis | None,
    evidence: list[EvidenceItem],
    hypotheses: list[dict[str, Any]],
    tool_summary: dict[str, int],
    unknowns: list[str],
) -> tuple[dict[str, Any], str]:
    label = {str(e.id): e.label for e in evidence}
    if analysis is None:
        overview = (
            "No relevant evidence was found in the connected sources for this question and time window."
            if not evidence
            else "Evidence was collected, but the analysis step did not complete."
        )
        facts: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        remediation: list[str] = []
    else:
        overview = analysis.overview or "Investigation summary unavailable."
        facts, diagnostics, remediation = analysis.facts, analysis.diagnostics, analysis.remediation
    content = {
        "investigation_id": str(inv.id),
        "version": 1,
        "overview": overview,
        "scope": scope,
        "observed_facts": facts,
        "hypotheses": hypotheses,
        "recommended_diagnostics": diagnostics,
        "proposed_remediation": remediation,
        "unknowns": unknowns,
        "tool_summary": tool_summary,
        # Transparency: model output that failed citation/number validation, with reasons.
        "removed_by_validation": analysis.removed if analysis else [],
        "generated_at": datetime.now(UTC).isoformat(),
    }

    def cite(ids: list[str]) -> str:
        return "".join(f"[{label[i]}]" for i in ids if i in label)

    md = [
        f"# Incident investigation: {inv.question}",
        "",
        f"_Scope:_ {scope}",
        "",
        "## Overview",
        "",
        overview,
        "",
    ]
    md += (
        ["## Observed facts", ""]
        + ([f"- {f['text']} {cite(f['evidence_ids'])}" for f in facts] or ["- None established."])
        + [""]
    )
    md += ["## Hypotheses (not confirmed)", ""]
    for i, h in enumerate(hypotheses, 1):
        md += [
            f"### {i}. {h['statement']} — _{h['status']}_",
            "",
            f"Supporting: {cite(h['supporting_evidence_ids']) or 'none'}  ",
            f"Contradicting: {cite(h['contradicting_evidence_ids']) or 'none'}",
            "",
            f"Why: {h['confidence_explanation']}",
            "",
        ]
        if h["missing_evidence"]:
            md += ["Missing evidence:"] + [f"- {m}" for m in h["missing_evidence"]] + [""]
        if h["validation_steps"]:
            md += ["How to validate:"] + [f"- {s}" for s in h["validation_steps"]] + [""]
    if not hypotheses:
        md += ["No hypothesis is supported by the collected evidence.", ""]
    md += (
        ["## Recommended diagnostics", ""] + ([f"- {d}" for d in diagnostics] or ["- None."]) + [""]
    )
    md += ["## Proposed remediation", ""] + ([f"- {r}" for r in remediation] or ["- None."]) + [""]
    md += (
        ["## Unknowns and limitations", ""]
        + ([f"- {u}" for u in unknowns] or ["- None noted."])
        + [""]
    )
    md += [
        "## Tool execution summary",
        "",
        f"{tool_summary['total']} tool calls: {tool_summary['succeeded']} succeeded, {tool_summary['failed']} failed.",
        "",
    ]
    md += ["## Evidence", ""] + [
        f"- **{e.label}** ({e.source_system}) {e.title} — `{e.source_reference}`" for e in evidence
    ]
    return content, "\n".join(md) + "\n"
