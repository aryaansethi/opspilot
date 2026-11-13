"""Investigation, approval and audit endpoints (shapes match frontend/lib/types/api.ts)."""

import base64
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import record
from app.auth.deps import DB, Workspace, WorkspaceCtx
from app.auth.schemas import UserOut
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.documents import storage
from app.investigations import events as ev
from app.investigations.engine import hypothesis_dict
from app.investigations.params import validate_window
from app.mcp.invoker import invoke_tool
from app.models import (
    ActionApproval,
    AuditEvent,
    EvidenceItem,
    Hypothesis,
    Investigation,
    InvestigationReport,
    ToolInvocation,
    User,
)

router = APIRouter(tags=["investigations"])


# ------------------------------------------------------------------ schemas
class InvestigationCreate(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    service: str | None = Field(default=None, max_length=120)
    environment: str | None = Field(default=None, max_length=40)
    time_start: datetime | None = None
    time_end: datetime | None = None


class InvestigationContinue(BaseModel):
    service: str | None = Field(default=None, max_length=120)
    environment: str | None = Field(default=None, max_length=40)
    time_start: datetime | None = None
    time_end: datetime | None = None


class InvestigationOut(BaseModel):
    id: uuid.UUID
    question: str
    service: str | None
    environment: str | None
    time_start: datetime | None
    time_end: datetime | None
    incident_type: str | None
    state: str
    missing_parameters: list[str]
    failed_steps: list[str]
    error: str | None
    plan: dict[str, Any] | None
    created_by: UserOut | None
    created_at: datetime
    updated_at: datetime


class EvidenceOut(BaseModel):
    id: uuid.UUID
    label: str
    source_system: str
    title: str
    source_reference: str
    url: str | None
    excerpt: str
    observed_at: datetime | None
    time_range: dict[str, str] | None
    retrieval_method: str | None
    rank: int | None
    reliability_notes: str | None
    metadata: dict[str, Any]


class HypothesisOut(BaseModel):
    id: uuid.UUID
    statement: str
    status: str
    supporting_evidence_ids: list[uuid.UUID]
    contradicting_evidence_ids: list[uuid.UUID]
    missing_evidence: list[str]
    confidence_explanation: str
    validation_steps: list[str]


class ToolCallOut(BaseModel):
    id: uuid.UUID
    server: str
    tool: str
    access: str
    arguments_redacted: dict[str, Any]
    status: str
    duration_ms: int | None
    result_bytes: int | None
    truncated: bool
    error: str | None
    started_at: datetime


class ApprovalOut(BaseModel):
    id: uuid.UUID
    investigation_id: uuid.UUID
    kind: str
    tool: str
    server: str
    arguments: dict[str, Any]
    status: str
    requested_by: UserOut | None
    decided_by: UserOut | None
    decided_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime


class JiraIssueFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    issue_type: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=3, max_length=255)
    description: str = Field(max_length=20000)
    labels: list[Annotated[str, Field(max_length=50, pattern=r"^\S+$")]] = Field(
        default=[], max_length=10
    )


class ActionRequest(BaseModel):
    kind: Literal["create_jira_issue"]
    fields: JiraIssueFields


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


# ------------------------------------------------------------------ helpers
async def _users(db: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, UserOut]:
    real = {i for i in ids if i}
    if not real:
        return {}
    rows = await db.scalars(select(User).where(User.id.in_(real)))
    return {u.id: UserOut.model_validate(u) for u in rows}


async def _inv_out(
    db: AsyncSession, inv: Investigation, users: dict[uuid.UUID, UserOut] | None = None
) -> InvestigationOut:
    users = users if users is not None else await _users(db, {inv.created_by})
    return InvestigationOut(
        id=inv.id,
        question=inv.question,
        service=inv.service,
        environment=inv.environment,
        time_start=inv.time_start,
        time_end=inv.time_end,
        incident_type=inv.incident_type,
        state=inv.state,
        missing_parameters=inv.missing_parameters or [],
        failed_steps=inv.failed_steps or [],
        error=inv.error,
        plan=inv.plan,
        created_by=users.get(inv.created_by) if inv.created_by else None,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
    )


async def _get_inv(
    db: AsyncSession, ctx: WorkspaceCtx, investigation_id: uuid.UUID
) -> Investigation:
    inv = await db.scalar(
        select(Investigation).where(
            Investigation.id == investigation_id, Investigation.workspace_id == ctx.workspace_id
        )
    )
    if inv is None:
        raise NotFound("Investigation not found")
    return inv


async def _approval_out(db: AsyncSession, a: ActionApproval) -> ApprovalOut:
    users = await _users(db, {a.requested_by, a.decided_by})
    return ApprovalOut(
        id=a.id,
        investigation_id=a.investigation_id,
        kind=a.kind,
        tool=a.tool,
        server=a.server,
        arguments=a.arguments,
        status=a.status,
        requested_by=users.get(a.requested_by) if a.requested_by else None,
        decided_by=users.get(a.decided_by) if a.decided_by else None,
        decided_at=a.decided_at,
        result=a.result,
        error=a.error,
        created_at=a.created_at,
    )


def _cursor(created_at: datetime, ident: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{ident}".encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, ident = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(ident)
    except Exception:  # noqa: BLE001
        raise AppError("Invalid cursor") from None


async def _enqueue(inv: Investigation) -> None:
    await storage.enqueue(
        get_settings().sqs_investigate_queue,
        {"investigation_id": str(inv.id), "workspace_id": str(inv.workspace_id)},
    )


# ------------------------------------------------------------------ investigations
@router.post("/investigations", status_code=status.HTTP_202_ACCEPTED)
async def create_investigation(
    body: InvestigationCreate, db: DB, ctx: Workspace
) -> dict[str, uuid.UUID]:
    ctx.require_write()
    validate_window(body.time_start, body.time_end)
    inv = Investigation(
        workspace_id=ctx.workspace_id,
        created_by=ctx.user.id,
        question=body.question.strip(),
        service=(body.service or "").strip() or None,
        environment=(body.environment or "").strip() or None,
        time_start=body.time_start,
        time_end=body.time_end,
        state="RECEIVED",
    )
    db.add(inv)
    await db.flush()
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="investigation.created",
        target_type="investigation",
        target_id=inv.id,
        metadata={"service": inv.service},
    )
    await ev.emit(db, inv, "state_changed", {"from": None, "to": "RECEIVED"})
    await _enqueue(inv)
    return {"id": inv.id}


@router.get("/investigations", response_model=Page[InvestigationOut])
async def list_investigations(
    db: DB,
    ctx: Workspace,
    cursor: str | None = None,
    limit: int = Query(25, ge=1, le=100),
    state: str | None = None,
) -> Page[InvestigationOut]:
    q = select(Investigation).where(Investigation.workspace_id == ctx.workspace_id)
    if state:
        q = q.where(Investigation.state == state)
    if cursor:
        ts, ident = _decode(cursor)
        q = q.where(
            or_(
                Investigation.created_at < ts,
                and_(Investigation.created_at == ts, Investigation.id < ident),
            )
        )
    rows = list(
        await db.scalars(
            q.order_by(Investigation.created_at.desc(), Investigation.id.desc()).limit(limit + 1)
        )
    )
    more, rows = len(rows) > limit, rows[:limit]
    users = await _users(db, {r.created_by for r in rows})
    return Page[InvestigationOut](
        items=[await _inv_out(db, r, users) for r in rows],
        next_cursor=_cursor(rows[-1].created_at, rows[-1].id) if more else None,
    )


@router.get("/investigations/{investigation_id}", response_model=InvestigationOut)
async def get_investigation(
    investigation_id: uuid.UUID, db: DB, ctx: Workspace
) -> InvestigationOut:
    return await _inv_out(db, await _get_inv(db, ctx, investigation_id))


@router.post("/investigations/{investigation_id}/continue", response_model=InvestigationOut)
async def continue_investigation(
    investigation_id: uuid.UUID, body: InvestigationContinue, db: DB, ctx: Workspace
) -> InvestigationOut:
    ctx.require_write()
    inv = await _get_inv(db, ctx, investigation_id)
    if inv.state != "AWAITING_PARAMETERS":
        raise Conflict(f"Investigation is {inv.state}; it is not waiting for parameters")
    service = (body.service or "").strip() or inv.service
    start = body.time_start or inv.time_start
    end = body.time_end or inv.time_end
    validate_window(start, end)
    inv.service, inv.time_start, inv.time_end = service, start, end
    inv.environment = (body.environment or "").strip() or inv.environment
    inv.missing_parameters = []
    previous, inv.state = inv.state, "RECEIVED"
    await db.flush()
    await ev.emit(db, inv, "state_changed", {"from": previous, "to": "RECEIVED"})
    await _enqueue(inv)
    await db.refresh(inv)  # updated_at is set by the database on update
    return await _inv_out(db, inv)


@router.get("/investigations/{investigation_id}/events")
async def investigation_events(
    investigation_id: uuid.UUID,
    db: DB,
    ctx: Workspace,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    follow: bool = True,
) -> StreamingResponse:
    await _get_inv(db, ctx, investigation_id)
    try:
        after = max(0, int(last_event_id)) if last_event_id else 0
    except ValueError:
        after = 0
    return StreamingResponse(
        ev.stream(db, investigation_id, after, follow=follow),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/investigations/{investigation_id}/evidence", response_model=list[EvidenceOut])
async def get_evidence(investigation_id: uuid.UUID, db: DB, ctx: Workspace) -> list[EvidenceOut]:
    inv = await _get_inv(db, ctx, investigation_id)
    rows = await db.scalars(
        select(EvidenceItem)
        .where(
            EvidenceItem.investigation_id == inv.id, EvidenceItem.workspace_id == ctx.workspace_id
        )
        .order_by(EvidenceItem.created_at)
    )
    return [
        EvidenceOut(
            id=e.id,
            label=e.label,
            source_system=e.source_system,
            title=e.title,
            source_reference=e.source_reference,
            url=e.url,
            excerpt=e.excerpt,
            observed_at=e.observed_at,
            time_range=e.time_range,
            retrieval_method=e.retrieval_method,
            rank=e.rank,
            reliability_notes=e.reliability_notes,
            metadata={**e.item_metadata, "label": e.label},
        )
        for e in rows
    ]


@router.get("/investigations/{investigation_id}/hypotheses", response_model=list[HypothesisOut])
async def get_hypotheses(
    investigation_id: uuid.UUID, db: DB, ctx: Workspace
) -> list[dict[str, Any]]:
    inv = await _get_inv(db, ctx, investigation_id)
    rows = await db.scalars(
        select(Hypothesis)
        .where(Hypothesis.investigation_id == inv.id)
        .order_by(Hypothesis.position)
    )
    return [hypothesis_dict(h) for h in rows]


@router.get("/investigations/{investigation_id}/tool-calls", response_model=list[ToolCallOut])
async def get_tool_calls(investigation_id: uuid.UUID, db: DB, ctx: Workspace) -> list[ToolCallOut]:
    inv = await _get_inv(db, ctx, investigation_id)
    rows = await db.scalars(
        select(ToolInvocation)
        .where(
            ToolInvocation.investigation_id == inv.id,
            ToolInvocation.workspace_id == ctx.workspace_id,
        )
        .order_by(ToolInvocation.created_at)
    )
    return [
        ToolCallOut(
            id=t.id,
            server=t.server_name,
            tool=t.tool_name,
            access=t.access,
            arguments_redacted=t.arguments_redacted,
            status="denied" if t.status == "rejected" else t.status,
            duration_ms=t.duration_ms,
            result_bytes=t.result_bytes,
            truncated=t.truncated,
            error=t.error,
            started_at=t.created_at,
        )
        for t in rows
    ]


@router.get("/investigations/{investigation_id}/report")
async def get_report(investigation_id: uuid.UUID, db: DB, ctx: Workspace) -> dict[str, Any]:
    inv = await _get_inv(db, ctx, investigation_id)
    rep = await db.scalar(
        select(InvestigationReport)
        .where(InvestigationReport.investigation_id == inv.id)
        .order_by(InvestigationReport.version.desc())
        .limit(1)
    )
    if rep is None:
        raise NotFound("No report yet")
    return {**rep.content, "markdown": rep.markdown}


# ------------------------------------------------------------------ approvals
@router.post(
    "/investigations/{investigation_id}/actions",
    response_model=ApprovalOut,
    status_code=status.HTTP_201_CREATED,
)
async def request_action(
    investigation_id: uuid.UUID, body: ActionRequest, db: DB, ctx: Workspace
) -> ApprovalOut:
    ctx.require_write()
    inv = await _get_inv(db, ctx, investigation_id)
    has_report = await db.scalar(
        select(InvestigationReport.id)
        .where(InvestigationReport.investigation_id == inv.id)
        .limit(1)
    )
    if has_report is None:
        raise Conflict("Actions can be requested once the report is ready")
    a = ActionApproval(
        workspace_id=ctx.workspace_id,
        investigation_id=inv.id,
        kind=body.kind,
        server="jira",
        tool="create_issue",
        arguments=body.fields.model_dump(),
        status="pending",
        requested_by=ctx.user.id,
    )
    db.add(a)
    await db.flush()
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="approval.requested",
        target_type="action_approval",
        target_id=a.id,
        metadata={"kind": a.kind, "arguments": a.arguments},
    )
    await ev.emit(db, inv, "approval_requested", {"approval_id": str(a.id), "kind": a.kind})
    return await _approval_out(db, a)


@router.get("/investigations/{investigation_id}/approvals", response_model=list[ApprovalOut])
async def investigation_approvals(
    investigation_id: uuid.UUID, db: DB, ctx: Workspace
) -> list[ApprovalOut]:
    inv = await _get_inv(db, ctx, investigation_id)
    rows = await db.scalars(
        select(ActionApproval)
        .where(ActionApproval.investigation_id == inv.id)
        .order_by(ActionApproval.created_at)
    )
    return [await _approval_out(db, a) for a in rows]


@router.get("/approvals", response_model=list[ApprovalOut])
async def list_approvals(
    db: DB, ctx: Workspace, status_filter: str | None = Query(default=None, alias="status")
) -> list[ApprovalOut]:
    q = select(ActionApproval).where(ActionApproval.workspace_id == ctx.workspace_id)
    if status_filter:
        q = q.where(ActionApproval.status == status_filter)
    rows = await db.scalars(q.order_by(ActionApproval.created_at.desc()).limit(100))
    return [await _approval_out(db, a) for a in rows]


async def _pending(db: AsyncSession, ctx: WorkspaceCtx, approval_id: uuid.UUID) -> ActionApproval:
    a = await db.scalar(
        select(ActionApproval)
        .where(ActionApproval.id == approval_id, ActionApproval.workspace_id == ctx.workspace_id)
        .with_for_update()
    )
    if a is None:
        raise NotFound("Approval not found")
    if a.status != "pending":
        raise Conflict(f"This action was already {a.status}")
    return a


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
async def approve(approval_id: uuid.UUID, db: DB, ctx: Workspace) -> ApprovalOut:
    if ctx.role == "viewer":
        raise Forbidden("Viewers cannot approve actions")
    user_id = ctx.user.id
    a = await _pending(db, ctx, approval_id)
    a.status, a.decided_by, a.decided_at = "approved", ctx.user.id, datetime.now(UTC)
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="approval.approved",
        target_type="action_approval",
        target_id=a.id,
        metadata={"kind": a.kind},
    )
    await db.commit()
    # Execute exactly the stored arguments; permissions are rechecked inside invoke_tool.
    try:
        r = await invoke_tool(
            db,
            ctx,
            f"{a.server}.{a.tool}",
            a.arguments,
            investigation_id=a.investigation_id,
            approved_action_id=a.id,
        )
        if r.status == "succeeded":
            a.status, a.result = "executed", r.data
        else:
            a.status, a.error = "failed", r.error
    except (NotFound, Forbidden) as e:
        # Raised before anything is written: the tool is unknown, disabled or not connected.
        a.status, a.error = "failed", f"Not executed: {e.message}"
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=user_id,
        action=f"approval.{a.status}",
        target_type="action_approval",
        target_id=a.id,
        metadata={"error": a.error},
    )
    await db.commit()
    return await _approval_out(db, a)


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalOut)
async def reject(approval_id: uuid.UUID, db: DB, ctx: Workspace) -> ApprovalOut:
    if ctx.role == "viewer":
        raise Forbidden("Viewers cannot reject actions")
    a = await _pending(db, ctx, approval_id)
    a.status, a.decided_by, a.decided_at = "rejected", ctx.user.id, datetime.now(UTC)
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="approval.rejected",
        target_type="action_approval",
        target_id=a.id,
        metadata={"kind": a.kind},
    )
    await db.commit()
    return await _approval_out(db, a)


# ------------------------------------------------------------------ audit log
class AuditOut(BaseModel):
    id: uuid.UUID
    actor: UserOut | None
    action: str
    target_type: str
    target_id: uuid.UUID | None
    metadata: dict[str, Any]
    created_at: datetime


@router.get("/audit-events", response_model=Page[AuditOut])
async def audit_events(
    db: DB,
    ctx: Workspace,
    actor: str | None = None,
    action: str | None = None,
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> Page[AuditOut]:
    q = select(AuditEvent).where(AuditEvent.workspace_id == ctx.workspace_id)
    if action:
        q = q.where(AuditEvent.action.ilike(f"{action}%"))
    if actor:
        try:
            q = q.where(AuditEvent.actor_user_id == uuid.UUID(actor))
        except ValueError:
            q = q.join(User, User.id == AuditEvent.actor_user_id).where(
                User.email.ilike(f"%{actor}%")
            )
    if from_:
        q = q.where(AuditEvent.created_at >= from_)
    if to:
        q = q.where(AuditEvent.created_at <= to)
    if cursor:
        ts, ident = _decode(cursor)
        q = q.where(
            or_(
                AuditEvent.created_at < ts, and_(AuditEvent.created_at == ts, AuditEvent.id < ident)
            )
        )
    rows = list(
        await db.scalars(
            q.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
        )
    )
    more, rows = len(rows) > limit, rows[:limit]
    users = await _users(db, {r.actor_user_id for r in rows})
    return Page[AuditOut](
        items=[
            AuditOut(
                id=r.id,
                actor=users.get(r.actor_user_id) if r.actor_user_id else None,
                action=r.action,
                target_type=r.target_type,
                target_id=r.target_id,
                metadata=r.event_metadata,
                created_at=r.created_at,
            )
            for r in rows
        ],
        next_cursor=_cursor(rows[-1].created_at, rows[-1].id) if more else None,
    )
