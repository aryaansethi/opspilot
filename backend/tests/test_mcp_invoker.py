"""Backend MCP layer: registry sync, policy, validation, size caps, timeouts, audit."""

import asyncio
import importlib.util
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from mcp.server.mcpserver import MCPServer

os.environ.setdefault("CW_ALLOWED_LOG_GROUPS", "/ecs/orders-api")
os.environ.setdefault("CW_ALLOWED_NAMESPACES", "OpsPilot/OrdersApi")

from app.mcp.connection import override_server  # noqa: E402
from app.mcp.invoker import cap_size, redact  # noqa: E402
from mcp_servers.cloudwatch.server import mcp as cloudwatch_mcp  # noqa: E402
from tests.conftest import register  # noqa: E402
from tests.test_documents import ws_headers  # noqa: E402

API = "/api/v1"

# A fake "github" server that also advertises an unreviewed write tool and a slow tool.
fake_github = MCPServer(name="fake-github")


@fake_github.tool()
async def list_recent_commits(repository: str, limit: int = 5) -> dict[str, Any]:
    return {"commits": [{"sha": f"{i:040x}", "message": f"commit {i}"} for i in range(limit)]}


@fake_github.tool()
async def delete_repository(repository: str) -> dict[str, Any]:  # not in the catalog
    return {"deleted": repository}


@fake_github.tool()
async def search_code(repository: str, query: str) -> dict[str, Any]:
    await asyncio.sleep(30)
    return {}


@pytest.fixture(scope="module", autouse=True)
def seeded() -> None:
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_cloudwatch.py"
    spec = importlib.util.spec_from_file_location("seed_cloudwatch", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


@pytest.fixture(autouse=True)
def in_process_servers() -> AsyncIterator[None]:
    override_server("cloudwatch", cloudwatch_mcp)
    override_server("github", fake_github)
    yield  # type: ignore[misc]
    override_server("cloudwatch", None)
    override_server("github", None)


def window() -> dict[str, str]:
    end = datetime.now(UTC) + timedelta(minutes=1)
    return {"start_time": (end - timedelta(hours=3)).isoformat(), "end_time": end.isoformat()}


async def setup(client: AsyncClient, connect: tuple[str, ...] = ("cloudwatch",)) -> dict[str, Any]:
    u = await register(client)
    h = ws_headers(u)
    sync = (await client.post(f"{API}/tools/sync", headers=h)).json()
    assert sync["cloudwatch"]["filter_log_events"] == "enabled"
    configs = {
        "cloudwatch": {"log_groups": ["/ecs/orders-api"], "namespaces": ["OpsPilot/OrdersApi"]},
        "github": {"repositories": ["acme/orders-api"]},
    }
    for kind in connect:
        r = await client.post(
            f"{API}/integrations", headers=h, json={"kind": kind, "config": configs[kind]}
        )
        assert r.status_code == 201, r.text
    return {**u, "h": h, "sync": sync}


async def invoke(client: AsyncClient, h: dict[str, str], tool: str, args: dict[str, Any]) -> Any:
    return await client.post(
        f"{API}/tools/invoke", headers=h, json={"tool": tool, "arguments": args}
    )


async def test_registry_enables_only_catalogued_tools(client: AsyncClient) -> None:
    u = await setup(client)
    gh = u["sync"]["github"]
    assert gh["list_recent_commits"] == "enabled"
    assert gh["delete_repository"] == "disabled_unknown"
    r = await invoke(client, u["h"], "github.delete_repository", {"repository": "acme/orders-api"})
    assert r.status_code == 403


async def test_read_tool_returns_live_evidence_and_is_audited(client: AsyncClient) -> None:
    u = await setup(client)
    r = await invoke(
        client,
        u["h"],
        "cloudwatch.filter_log_events",
        {"log_group": "/ecs/orders-api", "filter_pattern": "deploy", **window()},
    )
    body = r.json()
    assert r.status_code == 200 and body["status"] == "succeeded", body
    assert "release 4.3" in body["data"]["events"][0]["message"]
    audit = (await client.get(f"{API}/tool-invocations", headers=u["h"])).json()
    assert audit[0]["tool_name"] == "filter_log_events" and audit[0]["status"] == "succeeded"
    assert audit[0]["arguments_redacted"]["log_group"] == "/ecs/orders-api"


async def test_integration_must_be_connected(client: AsyncClient) -> None:
    u = await setup(client, connect=())
    r = await invoke(client, u["h"], "cloudwatch.list_log_groups", {})
    assert r.status_code == 403 and "not connected" in r.json()["error"]["message"]


async def test_workspace_allowlist_and_schema_rejections_are_audited(client: AsyncClient) -> None:
    u = await setup(client)
    other_group = await invoke(
        client, u["h"], "cloudwatch.filter_log_events", {"log_group": "/ecs/payments", **window()}
    )
    assert other_group.json()["status"] == "rejected"
    assert "not enabled for this workspace" in other_group.json()["error"]
    bad_schema = await invoke(client, u["h"], "cloudwatch.filter_log_events", {"log_group": 42})
    assert (
        bad_schema.json()["status"] == "rejected"
        and "Invalid arguments" in bad_schema.json()["error"]
    )
    statuses = [
        a["status"] for a in (await client.get(f"{API}/tool-invocations", headers=u["h"])).json()
    ]
    assert statuses.count("rejected") == 2


async def test_server_side_errors_surface_cleanly(client: AsyncClient) -> None:
    u = await setup(client)
    r = await invoke(
        client,
        u["h"],
        "cloudwatch.filter_log_events",
        {
            "log_group": "/ecs/orders-api",
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-05T00:00:00Z",
        },
    )
    assert r.json()["status"] == "failed" and "24 hours" in r.json()["error"]


async def test_timeout_is_enforced(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.mcp import catalog

    monkeypatch.setitem(
        catalog.CATALOG["github"], "search_code", catalog.ToolPolicy("read", 500, 64000)
    )
    u = await setup(client, connect=("cloudwatch", "github"))
    r = await invoke(
        client, u["h"], "github.search_code", {"repository": "acme/orders-api", "query": "pool"}
    )
    assert r.json()["status"] == "timeout"


async def test_cross_workspace_tool_use_blocked(client: AsyncClient) -> None:
    await setup(client)
    eve = await register(client, "eve@example.com")
    r = await invoke(client, ws_headers(eve), "cloudwatch.list_log_groups", {})
    assert r.status_code == 403


async def test_integration_test_endpoint_and_config_validation(client: AsyncClient) -> None:
    u = await setup(client)
    integ = (await client.get(f"{API}/integrations", headers=u["h"])).json()[0]
    tested = (await client.post(f"{API}/integrations/{integ['id']}/test", headers=u["h"])).json()
    assert tested["status"] == "connected" and any(
        t["name"] == "filter_log_events" for t in tested["tools"]
    )
    bad = await client.post(
        f"{API}/integrations",
        headers=u["h"],
        json={"kind": "github", "config": {"repositories": ["not a repo"]}},
    )
    assert bad.status_code == 400


def test_redaction_and_size_cap() -> None:
    assert redact({"github_token": "x", "nested": {"password": "y", "q": 1}}) == {
        "github_token": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "q": 1},
    }
    data = {"events": [{"message": "x" * 200} for _ in range(100)], "log_group": "g"}
    capped, truncated, size = cap_size(data, 5000)
    assert truncated and size <= 5000 and capped["_opspilot_truncated"]["field"] == "events"
    assert 0 < len(capped["events"]) < 100


async def test_github_connection_test_uses_configured_repo(client: AsyncClient) -> None:
    u = await setup(client, connect=("cloudwatch", "github"))
    gh = next(
        i
        for i in (await client.get(f"{API}/integrations", headers=u["h"])).json()
        if i["kind"] == "github"
    )
    tested = (await client.post(f"{API}/integrations/{gh['id']}/test", headers=u["h"])).json()
    assert tested["status"] == "connected"
    audit = (await client.get(f"{API}/tool-invocations", headers=u["h"])).json()
    assert audit[0]["arguments_redacted"] == {"repository": "acme/orders-api", "limit": 1}
