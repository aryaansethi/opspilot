"""Workspace integrations (opt-in to MCP servers, workspace allowlists) and tool access."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import jsonschema
from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.audit.service import record
from app.auth.deps import DB, Workspace
from app.core.errors import AppError, Conflict, Forbidden, NotFound
from app.mcp.catalog import INTEGRATION_CONFIG_SCHEMAS
from app.mcp.invoker import invoke_tool
from app.mcp.registry import sync_all
from app.models import ConnectedIntegration, McpServer, ToolInvocation, ToolRegistryEntry

router = APIRouter(tags=["integrations"])


def _health_check(kind: str, config: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Cheapest read call per integration, used by "test connection"."""
    if kind == "cloudwatch":
        return "cloudwatch.list_log_groups", {}
    if kind == "github" and config.get("repositories"):
        return "github.list_recent_commits", {"repository": config["repositories"][0], "limit": 1}
    return None


class ToolOut(BaseModel):
    name: str
    qualified_name: str
    description: str
    access: str
    enabled: bool
    requires_approval: bool


class IntegrationOut(BaseModel):
    id: uuid.UUID
    kind: str
    status: str
    config: dict[str, Any]
    last_checked_at: datetime | None
    last_error: str | None
    tools: list[ToolOut]


class IntegrationCreate(BaseModel):
    kind: Literal["github", "cloudwatch"]
    config: dict[str, Any]


async def _tools_for(db: DB, kind: str) -> list[ToolOut]:
    rows = await db.scalars(
        select(ToolRegistryEntry)
        .join(McpServer, McpServer.id == ToolRegistryEntry.server_id)
        .where(McpServer.kind == kind)
        .order_by(ToolRegistryEntry.name)
    )
    return [
        ToolOut(
            name=t.name,
            qualified_name=f"{t.server.name}.{t.name}",
            description=t.description,
            access=t.access,
            enabled=t.enabled,
            requires_approval=t.requires_approval,
        )
        for t in rows
    ]


async def _out(db: DB, i: ConnectedIntegration) -> IntegrationOut:
    tools = await _tools_for(db, i.kind)
    for t in tools:
        t.enabled = t.enabled and t.name not in (i.disabled_tools or [])
    return IntegrationOut(
        id=i.id,
        kind=i.kind,
        status=i.status,
        config=i.config,
        last_checked_at=i.last_checked_at,
        last_error=i.last_error,
        tools=tools,
    )


@router.get("/integrations", response_model=list[IntegrationOut])
async def list_integrations(db: DB, ctx: Workspace) -> list[IntegrationOut]:
    rows = await db.scalars(
        select(ConnectedIntegration).where(ConnectedIntegration.workspace_id == ctx.workspace_id)
    )
    return [await _out(db, i) for i in rows]


@router.post("/integrations", response_model=IntegrationOut, status_code=status.HTTP_201_CREATED)
async def create_integration(body: IntegrationCreate, db: DB, ctx: Workspace) -> IntegrationOut:
    if ctx.role != "owner":
        raise Forbidden("Only workspace owners can connect integrations")
    try:
        jsonschema.validate(body.config, INTEGRATION_CONFIG_SCHEMAS[body.kind])
    except jsonschema.ValidationError as e:
        raise AppError(f"Invalid {body.kind} config: {e.message}") from None
    exists = await db.scalar(
        select(ConnectedIntegration).where(
            ConnectedIntegration.workspace_id == ctx.workspace_id,
            ConnectedIntegration.kind == body.kind,
        )
    )
    if exists:
        raise Conflict(f"{body.kind} is already connected; delete it first to change its config")
    i = ConnectedIntegration(workspace_id=ctx.workspace_id, kind=body.kind, config=body.config)
    db.add(i)
    await db.flush()
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="integration.connected",
        target_type="integration",
        target_id=i.id,
        metadata={"kind": body.kind, "config": body.config},
    )
    await db.commit()
    return await _out(db, i)


async def _get(db: DB, ctx: Workspace, integration_id: uuid.UUID) -> ConnectedIntegration:
    i = await db.scalar(
        select(ConnectedIntegration).where(
            ConnectedIntegration.id == integration_id,
            ConnectedIntegration.workspace_id == ctx.workspace_id,
        )
    )
    if i is None:
        raise NotFound("Integration not found")
    return i


@router.delete("/integrations/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(integration_id: uuid.UUID, db: DB, ctx: Workspace) -> None:
    if ctx.role != "owner":
        raise Forbidden("Only workspace owners can disconnect integrations")
    i = await _get(db, ctx, integration_id)
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="integration.disconnected",
        target_type="integration",
        target_id=i.id,
        metadata={"kind": i.kind},
    )
    await db.delete(i)
    await db.commit()


@router.post("/integrations/{integration_id}/test", response_model=IntegrationOut)
async def test_integration(integration_id: uuid.UUID, db: DB, ctx: Workspace) -> IntegrationOut:
    i = await _get(db, ctx, integration_id)
    health = _health_check(i.kind, i.config)
    if health is None:
        raise AppError(f"No connection test defined for {i.kind}")
    try:
        result = await invoke_tool(db, ctx, health[0], health[1])
        ok, error = result.status == "succeeded", result.error
    except (Forbidden, NotFound) as e:
        ok, error = False, e.message
    i.status = "connected" if ok else "error"
    i.last_error = None if ok else error
    i.last_checked_at = datetime.now(UTC)
    await db.commit()
    return await _out(db, i)


@router.post("/tools/sync")
async def sync_tools(db: DB, ctx: Workspace) -> dict[str, Any]:
    if ctx.role != "owner":
        raise Forbidden("Only workspace owners can sync the tool registry")
    return await sync_all(db)


class InvokeRequest(BaseModel):
    tool: str = Field(pattern=r"^[a-z_]+\.[a-z_]+$")
    arguments: dict[str, Any] = {}


class InvokeResponse(BaseModel):
    invocation_id: uuid.UUID
    tool: str
    status: str
    data: dict[str, Any] | None
    error: str | None
    duration_ms: int
    truncated: bool


@router.post("/tools/invoke", response_model=InvokeResponse)
async def invoke(body: InvokeRequest, db: DB, ctx: Workspace) -> InvokeResponse:
    """Run one READ tool directly (write tools are only reachable through approvals)."""
    r = await invoke_tool(db, ctx, body.tool, body.arguments)
    return InvokeResponse(
        invocation_id=r.invocation_id,
        tool=r.tool,
        status=r.status,
        data=r.data,
        error=r.error,
        duration_ms=r.duration_ms,
        truncated=r.truncated,
    )


class InvocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    server_name: str
    tool_name: str
    access: str
    arguments_redacted: dict[str, Any]
    status: str
    duration_ms: int | None
    result_bytes: int | None
    truncated: bool
    error: str | None
    investigation_id: uuid.UUID | None
    created_at: datetime


@router.get("/tool-invocations", response_model=list[InvocationOut])
async def list_invocations(
    db: DB,
    ctx: Workspace,
    investigation_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
) -> list[ToolInvocation]:
    q = select(ToolInvocation).where(ToolInvocation.workspace_id == ctx.workspace_id)
    if investigation_id:
        q = q.where(ToolInvocation.investigation_id == investigation_id)
    return list(await db.scalars(q.order_by(ToolInvocation.created_at.desc()).limit(limit)))


class ToolSwitch(BaseModel):
    enabled: bool


@router.patch("/integrations/{integration_id}/tools/{tool}", response_model=IntegrationOut)
async def set_tool_enabled(
    integration_id: uuid.UUID, tool: str, body: ToolSwitch, db: DB, ctx: Workspace
) -> IntegrationOut:
    """Workspace owners can switch a registered tool off (or back on) for their workspace only."""
    if ctx.role != "owner":
        raise Forbidden("Only workspace owners can change tool settings")
    i = await _get(db, ctx, integration_id)
    known = {t.name: t for t in await _tools_for(db, i.kind)}
    if tool not in known:
        raise NotFound(f"Tool '{tool}' is not registered for {i.kind}")
    if body.enabled and not known[tool].enabled:
        raise Forbidden(f"Tool '{tool}' is disabled globally and cannot be enabled per workspace")
    disabled = set(i.disabled_tools or [])
    if body.enabled:
        disabled.discard(tool)
    else:
        disabled.add(tool)
    i.disabled_tools = sorted(disabled)
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="integration.tool_toggled",
        target_type="integration",
        target_id=i.id,
        metadata={"tool": tool, "enabled": body.enabled},
    )
    await db.commit()
    return await _out(db, i)
