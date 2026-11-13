"""Sync the server-side tool registry with what each MCP server advertises."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import log
from app.mcp.catalog import CATALOG
from app.mcp.connection import connect, server_urls
from app.models import McpServer, ToolRegistryEntry


async def ensure_servers(db: AsyncSession) -> list[McpServer]:
    servers = []
    for name, url in server_urls().items():
        row = await db.scalar(select(McpServer).where(McpServer.name == name))
        if row is None:
            row = McpServer(name=name, kind=name, url=url, enabled=True)
            db.add(row)
        else:
            row.url = url
        servers.append(row)
    await db.commit()
    return servers


async def sync_server(db: AsyncSession, server: McpServer) -> dict[str, str]:
    """Returns {tool_name: outcome}. Raises if the server is unreachable."""
    async with connect(server.name, server.url, read_timeout_seconds=10) as client:
        listed = await client.list_tools()
    tools = listed.tools
    policy = CATALOG.get(server.kind, {})
    existing = {
        t.name: t
        for t in await db.scalars(
            select(ToolRegistryEntry).where(ToolRegistryEntry.server_id == server.id)
        )
    }
    outcome: dict[str, str] = {}
    seen = set()
    for tool in tools:
        seen.add(tool.name)
        p = policy.get(tool.name)
        row = existing.get(tool.name) or ToolRegistryEntry(server_id=server.id, name=tool.name)
        row.description = tool.description or ""
        row.input_schema = dict(tool.input_schema or {})
        if p is None:
            row.access, row.enabled, row.requires_approval = "unknown", False, True
            outcome[tool.name] = "disabled_unknown"
        else:
            row.access = p.access
            row.timeout_ms, row.max_result_bytes = p.timeout_ms, p.max_result_bytes
            row.requires_approval = p.requires_approval or p.access == "write"
            row.enabled = True
            outcome[tool.name] = "enabled"
        db.add(row)
    for name, row in existing.items():
        if name not in seen:
            row.enabled = False
            outcome[name] = "disabled_missing"
    server.last_synced_at = datetime.now(UTC)
    await db.commit()
    log.info("mcp.registry_synced", server=server.name, tools=outcome)
    return outcome


async def sync_all(db: AsyncSession) -> dict[str, dict[str, str] | str]:
    result: dict[str, dict[str, str] | str] = {}
    for server in await ensure_servers(db):
        try:
            result[server.name] = await sync_server(db, server)
        except Exception as e:  # noqa: BLE001
            await db.rollback()
            result[server.name] = f"unreachable: {type(e).__name__}"
            log.warning("mcp.sync_failed", server=server.name, error=repr(e))
    return result
