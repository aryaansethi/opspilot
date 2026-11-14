"""MCP integrations fail clearly: bad responses, network errors, denied permissions, servers down."""

import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError
from httpx import AsyncClient
from mcp import Client

os.environ.setdefault("CW_ALLOWED_LOG_GROUPS", "/ecs/orders-api")
os.environ.setdefault("CW_ALLOWED_NAMESPACES", "OpsPilot/OrdersApi")

from app.mcp.connection import override_server  # noqa: E402
from mcp_servers.cloudwatch import server as cw  # noqa: E402
from mcp_servers.github import server as gh  # noqa: E402
from tests.test_mcp_invoker import invoke, setup  # noqa: E402

REPO = "acme/orders-api"
WINDOW = {"start_time": "2026-11-13T07:00:00Z", "end_time": "2026-11-13T09:00:00Z"}


@pytest.fixture
def github_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_ALLOWED_REPOS", REPO)
    yield
    gh.set_transport(None)


async def gh_call(handler: Any) -> str:
    gh.set_transport(httpx.MockTransport(handler))
    async with Client(gh.mcp) as c:
        r = await c.call_tool("list_recent_commits", {"repository": REPO})
    assert r.is_error
    return str(r.content[0].text)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        (
            lambda req: httpx.Response(502, text="<html>bad gateway</html>"),
            "temporary GitHub error",
        ),
        (lambda req: httpx.Response(200, text="not json"), "not valid JSON"),
        (lambda req: httpx.Response(418, json={}), "unexpected status 418"),
    ],
)
async def test_github_bad_responses(github_env: None, handler: Any, message: str) -> None:
    assert message in await gh_call(handler)


async def test_github_network_failures(github_env: None) -> None:
    def refuse(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    def slow(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    assert "unreachable" in await gh_call(refuse)
    assert "did not respond in time" in await gh_call(slow)


class FailingAWS:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def __getattr__(self, name: str) -> Any:
        def fail(**kwargs: Any) -> Any:
            raise self.exc

        return fail


def client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "secret-ish details"}}, "FilterLogEvents"
    )


@pytest.mark.parametrize(
    ("exc", "message"),
    [
        (client_error("AccessDeniedException"), "AWS denied logs:filter_log_events"),
        (client_error("ThrottlingException"), "throttled"),
        (NoCredentialsError(), "No AWS credentials found"),
        (EndpointConnectionError(endpoint_url="https://logs.example"), "unreachable"),
        (client_error("SomethingOdd"), "AWS error SomethingOdd"),
    ],
)
async def test_cloudwatch_aws_failures_are_explained(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, message: str
) -> None:
    monkeypatch.setattr(cw, "_client", lambda service: FailingAWS(exc))
    async with Client(cw.mcp) as c:
        r = await c.call_tool("filter_log_events", {"log_group": "/ecs/orders-api", **WINDOW})
    text = str(r.content[0].text)  # type: ignore[union-attr]
    assert r.is_error and message in text and "secret-ish" not in text


async def test_mcp_server_down_is_a_clean_failure(client: AsyncClient) -> None:
    from mcp_servers.cloudwatch.server import mcp as cloudwatch_mcp
    from tests.test_mcp_invoker import fake_github

    override_server(
        "cloudwatch", cloudwatch_mcp
    )  # registry sync must not depend on a running server
    override_server("github", fake_github)
    try:
        u = await setup(client)
    finally:
        override_server("github", None)
    override_server("cloudwatch", "http://127.0.0.1:9/mcp")  # nothing listens on port 9
    try:
        r = await invoke(client, u["h"], "cloudwatch.list_log_groups", {})
    finally:
        override_server("cloudwatch", None)
    assert (
        r.status_code == 200
        and r.json()["status"] == "failed"
        and "MCP server error" in r.json()["error"]
    )
    audit = (await client.get("/api/v1/tool-invocations", headers=u["h"])).json()
    assert audit[0]["status"] == "failed"
