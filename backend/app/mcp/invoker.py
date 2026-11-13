"""The single choke point for every MCP tool call.

Order of checks: registry (exists + enabled) → access policy (writes need an
approved action) → workspace integration connected → JSON-schema validation →
workspace argument policy → call with timeout → size cap → audit row.
"""

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceCtx
from app.core.errors import AppError, Forbidden, NotFound
from app.core.logging import log
from app.mcp.catalog import check_arguments_against_workspace
from app.mcp.connection import connect
from app.models import ConnectedIntegration, McpServer, ToolInvocation, ToolRegistryEntry

_SECRET_KEY = re.compile(r"(token|secret|password|authorization|api_key|credential)", re.I)


@dataclass
class ToolResult:
    invocation_id: uuid.UUID
    tool: str
    status: str  # succeeded | failed | timeout | rejected
    data: dict[str, Any] | None
    error: str | None
    duration_ms: int
    truncated: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if _SECRET_KEY.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def cap_size(data: dict[str, Any], max_bytes: int) -> tuple[dict[str, Any], bool, int]:
    """Trim the longest list in the result until it fits. Returns (data, truncated, bytes)."""
    raw = json.dumps(data, default=str)
    if len(raw.encode()) <= max_bytes:
        return data, False, len(raw.encode())
    data = json.loads(raw)
    lists = [(k, v) for k, v in data.items() if isinstance(v, list)]
    if not lists:
        return {"error": "result exceeded size limit", "size_bytes": len(raw.encode())}, True, 0
    key, items = max(lists, key=lambda kv: len(json.dumps(kv[1], default=str)))
    while items and len(json.dumps(data, default=str).encode()) > max_bytes:
        items = items[: max(0, int(len(items) * 0.75))]
        data[key] = items
    data["_opspilot_truncated"] = {"field": key, "kept": len(items)}
    size = len(json.dumps(data, default=str).encode())
    return data, True, size


def split_name(qualified: str) -> tuple[str, str]:
    if "." not in qualified:
        raise AppError(
            "Tool names are qualified as '<server>.<tool>', e.g. cloudwatch.filter_log_events"
        )
    server, tool = qualified.split(".", 1)
    return server, tool


async def invoke_tool(
    db: AsyncSession,
    ctx: WorkspaceCtx,
    qualified_name: str,
    arguments: dict[str, Any],
    *,
    investigation_id: uuid.UUID | None = None,
    approved_action_id: uuid.UUID | None = None,
) -> ToolResult:
    server_name, tool_name = split_name(qualified_name)
    entry = await db.scalar(
        select(ToolRegistryEntry)
        .join(McpServer, McpServer.id == ToolRegistryEntry.server_id)
        .where(McpServer.name == server_name, ToolRegistryEntry.name == tool_name)
    )
    if entry is None:
        raise NotFound(f"Tool '{qualified_name}' is not registered")
    if not entry.enabled or not entry.server.enabled:
        raise Forbidden(f"Tool '{qualified_name}' is disabled")
    if (entry.access != "read" or entry.requires_approval) and approved_action_id is None:
        raise Forbidden(
            f"Tool '{qualified_name}' changes external state and requires an approved action"
        )

    integration = await db.scalar(
        select(ConnectedIntegration).where(
            ConnectedIntegration.workspace_id == ctx.workspace_id,
            ConnectedIntegration.kind == entry.server.kind,
        )
    )
    if integration is None:
        raise Forbidden(f"The {entry.server.kind} integration is not connected for this workspace")

    invocation = ToolInvocation(
        workspace_id=ctx.workspace_id,
        investigation_id=investigation_id,
        actor_user_id=ctx.user.id,
        tool_id=entry.id,
        server_name=server_name,
        tool_name=tool_name,
        access=entry.access,
        arguments_redacted=redact(arguments),
        status="running",
    )
    db.add(invocation)
    await db.flush()

    def finish(
        status: str,
        data: dict[str, Any] | None,
        error: str | None,
        started: float,
        truncated: bool = False,
        size: int | None = None,
    ) -> ToolResult:
        duration = int((time.perf_counter() - started) * 1000)
        invocation.status, invocation.error = status, error
        invocation.duration_ms, invocation.result_bytes, invocation.truncated = (
            duration,
            size,
            truncated,
        )
        return ToolResult(invocation.id, qualified_name, status, data, error, duration, truncated)

    started = time.perf_counter()
    try:
        jsonschema.validate(arguments, entry.input_schema or {"type": "object"})
        check_arguments_against_workspace(
            entry.server.kind, tool_name, arguments, integration.config
        )
    except jsonschema.ValidationError as e:
        result = finish("rejected", None, f"Invalid arguments: {e.message}", started)
        await db.commit()
        return result
    except AppError as e:
        result = finish("rejected", None, e.message, started)
        await db.commit()
        return result

    timeout = entry.timeout_ms / 1000
    try:
        async with asyncio.timeout(timeout):
            async with connect(
                server_name, entry.server.url, read_timeout_seconds=timeout
            ) as client:
                raw = await client.call_tool(tool_name, arguments)
    except TimeoutError:
        result = finish("timeout", None, f"Tool did not respond within {timeout:.0f}s", started)
        await db.commit()
        return result
    except Exception as e:  # noqa: BLE001
        log.warning("mcp.call_failed", tool=qualified_name, error=repr(e))
        result = finish("failed", None, f"MCP server error: {type(e).__name__}", started)
        await db.commit()
        return result

    if raw.is_error:
        text = " ".join(getattr(c, "text", "") for c in raw.content)[:500]
        result = finish("failed", None, text or "Tool reported an error", started)
        await db.commit()
        return result

    data = raw.structured_content
    if not isinstance(data, dict):
        data = {"content": [getattr(c, "text", str(c)) for c in raw.content]}
    data, truncated, size = cap_size(data, entry.max_result_bytes)
    result = finish("succeeded", data, None, started, truncated, size)
    await db.commit()
    return result
