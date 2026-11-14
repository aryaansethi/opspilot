"""Bounded investigation workflow (explicit state machine, no free-form agent loop).

RECEIVED → CLASSIFY_REQUEST → COLLECT_PARAMETERS (→ AWAITING_PARAMETERS) → PLAN_INVESTIGATION
→ RUN_KNOWLEDGE_RETRIEVAL → RUN_READ_TOOLS → NORMALIZE_EVIDENCE → ANALYZE_HYPOTHESES
→ CHECK_CITATIONS → GENERATE_REPORT → COMPLETED | PARTIAL   (or FAILED_LLM / FAILED_RETRIEVAL)

Limits: at most 2 LLM calls, `investigation_max_tool_calls` tool calls, and
`investigation_timeout_seconds` wall clock per run.
"""

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceCtx
from app.core.config import get_settings
from app.core.logging import log
from app.investigations import analysis as an
from app.investigations.collectors import Collector
from app.investigations.events import emit
from app.investigations.params import classify, missing_parameters
from app.investigations.report import build_report, scope_text
from app.jobs import claim_investigation
from app.models import (
    ConnectedIntegration,
    EvidenceItem,
    Hypothesis,
    Investigation,
    InvestigationReport,
    ToolInvocation,
    User,
    WorkspaceMember,
)
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.generation.llm import LLMError, LLMProvider


class _SkipPlanning(Exception):
    """Internal: planning is unnecessary (no live sources)."""


async def recover(db: AsyncSession, inv: Investigation) -> None:
    """Roll back a failed step and reload the investigation (rollback expires loaded objects)."""
    await db.rollback()
    await db.refresh(inv)


async def set_state(db: AsyncSession, inv: Investigation, state: str) -> None:
    previous, inv.state = inv.state, state
    await db.flush()
    await emit(db, inv, "state_changed", {"from": previous, "to": state})


async def _context(db: AsyncSession, inv: Investigation) -> WorkspaceCtx | None:
    if inv.created_by is None:
        return None
    user = await db.get(User, inv.created_by)
    member = await db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == inv.workspace_id,
            WorkspaceMember.user_id == inv.created_by,
        )
    )
    if user is None or member is None:
        return None
    return WorkspaceCtx(user=user, workspace_id=inv.workspace_id, role=member.role)


def allowed_tasks(integrations: dict[str, ConnectedIntegration]) -> list[str]:
    tasks = ["search_runbooks", "search_historical_incidents"]
    if "cloudwatch" in integrations:
        tasks += ["check_cloudwatch_alarms", "query_cloudwatch_logs", "query_cloudwatch_metrics"]
    if "github" in integrations:
        tasks.append("search_recent_github_commits")
    return tasks


async def run_investigation(
    db: AsyncSession, investigation_id: uuid.UUID, *, llm: LLMProvider, embedder: EmbeddingProvider
) -> str:
    before = await db.scalar(
        select(Investigation.state).where(Investigation.id == investigation_id)
    )
    if not await claim_investigation(db, investigation_id):
        # Unknown, finished, waiting for the user, or running in another worker right now.
        inv = await db.get(Investigation, investigation_id)
        return "missing" if inv is None else inv.state
    inv = await db.get(Investigation, investigation_id)
    if inv is None:
        return "missing"
    await db.refresh(inv)
    try:
        async with asyncio.timeout(get_settings().investigation_timeout_seconds):
            return await _run(db, inv, llm, embedder, claimed_from=before)
    except TimeoutError:
        await db.rollback()
        inv = await db.get(Investigation, investigation_id)
        assert inv is not None
        inv.error = f"Investigation exceeded {get_settings().investigation_timeout_seconds}s and was stopped."
        inv.failed_steps = [*inv.failed_steps, "timeout"]
        inv.finished_at = datetime.now(UTC)
        await emit(db, inv, "error", {"message": inv.error})
        await set_state(db, inv, "PARTIAL")
        return inv.state


async def _run(
    db: AsyncSession,
    inv: Investigation,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    claimed_from: str | None = None,
) -> str:
    # A (re)delivered run always starts clean.
    for model in (EvidenceItem, Hypothesis, InvestigationReport):
        await db.execute(delete(model).where(model.investigation_id == inv.id))  # type: ignore[attr-defined]
    inv.failed_steps, inv.error, inv.started_at, inv.finished_at = [], None, datetime.now(UTC), None
    inv.timings_ms = None
    await db.commit()
    timings: dict[str, float] = {}
    t_run = time.perf_counter()

    def lap(stage: str, started: float) -> None:
        timings[stage] = round((time.perf_counter() - started) * 1000, 1)

    # 1. classify (rule-based, instant). The claim already moved the state; report the real origin.
    await emit(db, inv, "state_changed", {"from": claimed_from, "to": "CLASSIFY_REQUEST"})
    inv.incident_type = inv.incident_type or classify(inv.question)

    # 2. parameters: ask instead of guessing a production scope
    await set_state(db, inv, "COLLECT_PARAMETERS")
    missing = missing_parameters(inv.service, inv.time_start, inv.time_end)
    if missing:
        inv.missing_parameters = missing
        await emit(db, inv, "parameters_required", {"missing": missing})
        await set_state(db, inv, "AWAITING_PARAMETERS")
        return inv.state
    inv.missing_parameters = []

    ctx = await _context(db, inv)
    if ctx is None:
        inv.error = "The user who started this investigation no longer has access to the workspace."
        await set_state(db, inv, "FAILED_INVALID_PARAMS")
        return inv.state
    integrations = {
        i.kind: i
        for i in await db.scalars(
            select(ConnectedIntegration).where(
                ConnectedIntegration.workspace_id == inv.workspace_id
            )
        )
    }

    # 3. plan (LLM call 1, validated; falls back to the default plan)
    await set_state(db, inv, "PLAN_INVESTIGATION")
    allowed = allowed_tasks(integrations)
    window = (
        f"{inv.time_start.isoformat()} to {inv.time_end.isoformat()}"
        if inv.time_start and inv.time_end
        else ""
    )
    context = {k: v.config for k, v in integrations.items()}
    t = time.perf_counter()
    try:
        if not any(task in an.LIVE_TASKS for task in allowed):
            # Only knowledge-base tasks are possible: an LLM plan could not change anything.
            plan = an.default_plan(inv.incident_type or "other", allowed)
            plan.source, plan.rationale = (
                "no_live_sources",
                "No live integrations connected; nothing to plan.",
            )
            raise _SkipPlanning
        raw = await an.run_plan(
            llm,
            an.plan_prompt(
                inv.question,
                inv.service or "",
                inv.environment,
                window,
                inv.incident_type or "other",
                allowed,
                context,
            ),
        )
        plan = an.validate_plan(raw, inv.incident_type or "other", allowed)
        lap("plan_llm", t)
    except _SkipPlanning:
        pass
    except (LLMError, Exception) as e:  # noqa: BLE001 - planning failure must not stop evidence gathering
        lap("plan_llm", t)
        log.warning("investigation.plan_failed", error=repr(e))
        plan = an.default_plan(inv.incident_type or "other", allowed)
        inv.failed_steps = [
            *inv.failed_steps,
            f"PLAN_INVESTIGATION: model plan unusable ({type(e).__name__}); default plan used",
        ]
    inv.incident_type = plan.incident_type
    inv.plan = {
        "tasks": plan.tasks,
        "log_search_terms": plan.log_search_terms,
        "rationale": plan.rationale,
        "source": plan.source,
        "allowed_tasks": allowed,
    }
    await emit(db, inv, "step_completed", {"step": "PLAN_INVESTIGATION", "plan": inv.plan})

    col = Collector(db=db, inv=inv, ctx=ctx, embedder=embedder, integrations=integrations)
    # Say which live sources were not consulted, so a quiet report is not mistaken for "all clear".
    for kind, what in (
        ("cloudwatch", "logs, metrics and alarms"),
        ("github", "recent code changes"),
    ):
        if kind not in integrations:
            col.notes.append(
                f"The {kind} integration is not connected, so {what} were not checked."
            )

    # 4. knowledge base
    await set_state(db, inv, "RUN_KNOWLEDGE_RETRIEVAL")
    t = time.perf_counter()
    try:
        if "search_runbooks" in plan.tasks:
            await col.knowledge(("runbook", "architecture", "other"), 4, "runbooks")
        if "search_historical_incidents" in plan.tasks:
            await col.knowledge(("incident_report",), 3, "historical_incidents")
    except Exception as e:  # noqa: BLE001
        await recover(db, inv)
        log.warning("investigation.retrieval_failed", error=repr(e))
        col.failed_steps.append(f"RUN_KNOWLEDGE_RETRIEVAL: {type(e).__name__}")
        await emit(
            db, inv, "step_failed", {"step": "RUN_KNOWLEDGE_RETRIEVAL", "error": type(e).__name__}
        )

    lap("knowledge_retrieval", t)

    # 5. read-only tools, cheapest/most informative first
    await set_state(db, inv, "RUN_READ_TOOLS")
    t = time.perf_counter()
    # Deploy/config lines are the most common explanation for regressions, so they are always
    # searched; the model's terms fill the remaining slot(s). ERROR is already summarised.
    extra = [t for t in plan.log_search_terms if t.upper() != "ERROR"]
    terms = list(dict.fromkeys(["deploy", "config", *extra]))[:3]
    steps = [
        ("check_cloudwatch_alarms", col.alarms),
        ("query_cloudwatch_logs", lambda: col.logs(terms)),
        ("query_cloudwatch_metrics", col.metrics),
        ("search_recent_github_commits", col.commits),
    ]
    for task, fn in steps:
        if task not in plan.tasks:
            continue
        await emit(db, inv, "step_started", {"step": task})
        try:
            await fn()
            await emit(db, inv, "step_completed", {"step": task})
        except Exception as e:  # noqa: BLE001 - one source failing must not sink the run
            await recover(db, inv)
            log.warning("investigation.task_failed", task=task, error=repr(e))
            col.failed_steps.append(f"{task}: {type(e).__name__}")
            await emit(db, inv, "step_failed", {"step": task, "error": type(e).__name__})

    if any(task in plan.tasks for task, _ in steps):
        lap("read_tools", t)

    # 6. evidence is normalised as it is collected
    await set_state(db, inv, "NORMALIZE_EVIDENCE")
    evidence = list(
        await db.scalars(
            select(EvidenceItem)
            .where(EvidenceItem.investigation_id == inv.id)
            .order_by(EvidenceItem.created_at)
        )
    )
    inv.failed_steps = [*inv.failed_steps, *col.failed_steps]
    sources = sorted({e.source_system for e in evidence})
    scope = scope_text(inv, sources)

    # 7-8. analysis (LLM call 2) + citation check
    analysis: an.ValidatedAnalysis | None = None
    llm_failed = False
    if evidence:
        await set_state(db, inv, "ANALYZE_HYPOTHESES")
        refs = [
            an.EvidenceRef(str(e.id), e.label, e.source_system, e.title, e.excerpt)
            for e in evidence
        ]
        t = time.perf_counter()
        try:
            raw = await an.run_analysis(llm, an.analysis_prompt(inv.question, scope, refs))
            lap("analysis_llm", t)
            await set_state(db, inv, "CHECK_CITATIONS")
            analysis = an.validate_analysis(raw, refs)
        except Exception as e:  # noqa: BLE001
            log.warning("investigation.analysis_failed", error=repr(e))
            llm_failed = True
            inv.error = (
                f"The language model could not produce a usable analysis ({type(e).__name__})."
            )
            await emit(
                db, inv, "step_failed", {"step": "ANALYZE_HYPOTHESES", "error": type(e).__name__}
            )

    hyp_rows: list[dict[str, Any]] = []
    if analysis:
        for i, h in enumerate(analysis.hypotheses):
            row = Hypothesis(
                workspace_id=inv.workspace_id,
                investigation_id=inv.id,
                position=i,
                statement=h.statement,
                status=h.status,
                supporting_evidence_ids=h.supporting,
                contradicting_evidence_ids=h.contradicting,
                missing_evidence=h.missing_evidence,
                confidence_explanation=h.confidence_explanation,
                validation_steps=h.validation_steps,
            )
            db.add(row)
            await db.flush()
            hyp_rows.append(hypothesis_dict(row))
            await emit(
                db,
                inv,
                "hypothesis_added",
                {"hypothesis_id": str(row.id), "statement": row.statement},
            )

    # 9. report
    await set_state(db, inv, "GENERATE_REPORT")
    t = time.perf_counter()
    statuses = list(
        await db.scalars(
            select(ToolInvocation.status).where(ToolInvocation.investigation_id == inv.id)
        )
    )
    tool_summary = {
        "total": len(statuses),
        "succeeded": statuses.count("succeeded"),
        "failed": len(statuses) - statuses.count("succeeded"),
    }
    no_live = bool(evidence) and not any(e.source_system in an.LIVE_SOURCES for e in evidence)
    live_note = (
        [
            "No live evidence (logs, metrics, alarms or commits) was found for this time window; "
            "findings rely on documentation and past incidents only."
        ]
        if no_live
        else []
    )
    unknowns = [
        *live_note,
        *(analysis.unknowns if analysis else []),
        *col.notes,
        *[f"Step did not complete: {s}" for s in inv.failed_steps],
    ]
    content, markdown = build_report(
        inv, scope, analysis, evidence, hyp_rows, tool_summary, unknowns
    )
    version = (
        await db.scalar(
            select(func.coalesce(func.max(InvestigationReport.version), 0)).where(
                InvestigationReport.investigation_id == inv.id
            )
        )
        or 0
    ) + 1
    content["version"] = version
    db.add(
        InvestigationReport(
            workspace_id=inv.workspace_id,
            investigation_id=inv.id,
            version=version,
            content=content,
            markdown=markdown,
        )
    )
    inv.finished_at = datetime.now(UTC)
    lap("report", t)
    lap("total", t_run)
    inv.timings_ms = timings
    await db.flush()
    await emit(db, inv, "report_ready", {"version": version})

    final = "FAILED_LLM" if llm_failed else ("PARTIAL" if inv.failed_steps else "COMPLETED")
    await set_state(db, inv, final)
    log.info(
        "investigation.finished",
        id=str(inv.id),
        state=final,
        evidence=len(evidence),
        hypotheses=len(hyp_rows),
        tools=tool_summary,
    )
    return final


def hypothesis_dict(h: Hypothesis) -> dict[str, Any]:
    return {
        "id": str(h.id),
        "statement": h.statement,
        "status": h.status,
        "supporting_evidence_ids": h.supporting_evidence_ids,
        "contradicting_evidence_ids": h.contradicting_evidence_ids,
        "missing_evidence": h.missing_evidence,
        "confidence_explanation": h.confidence_explanation,
        "validation_steps": h.validation_steps,
    }
