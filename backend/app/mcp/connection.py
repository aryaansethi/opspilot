"""Resolve where each MCP server lives. Tests can point a server at an in-process instance."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp import Client

from app.core.config import get_settings

_overrides: dict[str, Any] = {}


def server_urls() -> dict[str, str]:
    s = get_settings()
    return {"cloudwatch": s.mcp_cloudwatch_url, "github": s.mcp_github_url}


def override_server(name: str, target: Any | None) -> None:
    """Test hook: target is an MCPServer instance (in-process) or a URL; None clears."""
    if target is None:
        _overrides.pop(name, None)
    else:
        _overrides[name] = target


@asynccontextmanager
async def connect(
    name: str, url: str, read_timeout_seconds: float | None = None
) -> AsyncIterator[Client]:
    async with Client(
        _overrides.get(name, url), read_timeout_seconds=read_timeout_seconds
    ) as client:
        yield client
