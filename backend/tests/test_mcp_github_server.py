"""GitHub MCP server against a simulated GitHub REST API (no network, no token)."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from mcp import Client

from mcp_servers.github import server as gh

REPO = "acme/orders-api"
SHA = "a" * 40
seen: list[httpx.Request] = []


def fake_github(request: httpx.Request) -> httpx.Response:
    seen.append(request)
    p = request.url.path
    if request.headers.get("authorization") != "Bearer test-token":
        return httpx.Response(401, json={"message": "Bad credentials"})
    if p == "/repos/acme/empty/commits":
        return httpx.Response(409, json={"message": "Git Repository is empty."})
    if p == f"/repos/{REPO}/commits":
        return httpx.Response(
            200,
            json=[
                {
                    "sha": SHA,
                    "html_url": f"https://github.com/{REPO}/commit/{SHA}",
                    "commit": {
                        "message": "Release 4.3: lower hikari pool to 10",
                        "author": {"name": "Dev", "date": "2026-11-13T08:00:00Z"},
                    },
                }
            ],
        )
    if p == f"/repos/{REPO}/commits/{SHA}":
        return httpx.Response(
            200,
            json={
                "sha": SHA,
                "commit": {
                    "message": "Release 4.3",
                    "author": {"name": "Dev", "date": "2026-11-13T08:00:00Z"},
                },
                "stats": {"additions": 1, "deletions": 1},
                "files": [
                    {
                        "filename": "src/main/resources/application.yml",
                        "status": "modified",
                        "additions": 1,
                        "deletions": 1,
                        "patch": "-maximum-pool-size: 50\n+maximum-pool-size: 10" + "x" * 5000,
                    }
                ],
            },
        )
    if p == f"/repos/{REPO}/pulls":
        return httpx.Response(
            200,
            json=[
                {
                    "number": 7,
                    "title": "Tune pool",
                    "state": "closed",
                    "merged_at": "2026-11-13T07:55:00Z",
                    "user": {"login": "dev"},
                    "updated_at": "2026-11-13T07:55:00Z",
                    "html_url": "https://github.com/x/7",
                }
            ],
        )
    if p == f"/repos/{REPO}/pulls/7":
        return httpx.Response(
            200,
            json={
                "number": 7,
                "title": "Tune pool",
                "state": "closed",
                "body": "Lower pool size",
                "user": {"login": "dev"},
                "merge_commit_sha": SHA,
                "html_url": "https://github.com/x/7",
            },
        )
    if p == f"/repos/{REPO}/pulls/7/files":
        return httpx.Response(
            200, json=[{"filename": "application.yml", "status": "modified", "patch": "-50\n+10"}]
        )
    if p == "/search/code":
        return httpx.Response(
            200,
            json={
                "total_count": 1,
                "items": [{"path": "application.yml", "html_url": "u", "sha": "s"}],
            },
        )
    return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_ALLOWED_REPOS", REPO)
    gh.set_transport(httpx.MockTransport(fake_github))
    seen.clear()
    yield
    gh.set_transport(None)


@asynccontextmanager
async def connect() -> AsyncIterator[Client]:
    async with Client(gh.mcp) as c:
        yield c


async def ok(c: Client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    r = await c.call_tool(tool, args)
    assert not r.is_error, r.content
    return dict(r.structured_content)


async def test_commits_and_details() -> None:
    async with connect() as c:
        r = await ok(
            c,
            "list_recent_commits",
            {"repository": REPO, "since": "2026-11-13T00:00:00Z", "limit": 5},
        )
        assert r["commits"][0]["short_sha"] == "aaaaaaa" and "pool" in r["commits"][0]["message"]
        assert seen[-1].url.params["since"] == "2026-11-13T00:00:00Z"
        d = await ok(c, "get_commit_details", {"repository": REPO, "sha": SHA})
        f = d["files"][0]
        assert f["filename"].endswith("application.yml") and f["patch_truncated"] is True
        assert len(f["patch"]) == gh.MAX_PATCH_CHARS


async def test_pull_requests() -> None:
    async with connect() as c:
        prs = await ok(c, "list_pull_requests", {"repository": REPO})
        assert prs["pull_requests"][0]["number"] == 7
        pr = await ok(c, "get_pull_request", {"repository": REPO, "number": 7})
        assert pr["merge_commit_sha"] == SHA and pr["files"][0]["patch"] == "-50\n+10"


async def test_search_cannot_escape_repository() -> None:
    async with connect() as c:
        await ok(
            c,
            "search_code",
            {"repository": REPO, "query": "maximum-pool-size repo:torvalds/linux org:evil"},
        )
        q = seen[-1].url.params["q"]
        assert q == f"maximum-pool-size repo:{REPO}"


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("list_recent_commits", {"repository": "other/repo"}, "not allowlisted"),
        ("get_commit_details", {"repository": REPO, "sha": "f" * 40}, "404"),
        ("list_recent_commits", {"repository": REPO, "since": "2026-11-13T00:00:00"}, "timezone"),
    ],
)
async def test_rejections(tool: str, args: dict[str, Any], message: str) -> None:
    async with connect() as c:
        r = await c.call_tool(tool, args)
        assert r.is_error and message in r.content[0].text  # type: ignore[union-attr]


async def test_bad_token_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "wrong")
    async with connect() as c:
        r = await c.call_tool("list_recent_commits", {"repository": REPO})
        assert r.is_error and "401" in r.content[0].text  # type: ignore[union-attr]


async def test_invalid_sha_rejected_by_schema() -> None:
    async with connect() as c:
        r = await c.call_tool("get_commit_details", {"repository": REPO, "sha": "../../etc"})
        assert r.is_error
    assert not seen  # never reached GitHub


async def test_no_tool_accepts_or_returns_credentials() -> None:
    tools = await gh.mcp.list_tools()
    props = {p for t in tools for p in (t.input_schema or {}).get("properties", {})}
    assert not any("token" in p or "auth" in p for p in props)
    async with connect() as c:
        r = await ok(c, "get_pull_request", {"repository": REPO, "number": 7})
    assert "test-token" not in str(r)


async def test_empty_repository_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_ALLOWED_REPOS", f"{REPO},acme/empty")
    async with connect() as c:
        r = await ok(c, "list_recent_commits", {"repository": "acme/empty"})
    assert r["commits"] == [] and "no commits" in r["note"]


@pytest.mark.parametrize("missing", ["GITHUB_TOKEN", "GITHUB_ALLOWED_REPOS"])
async def test_unconfigured_server_explains_instead_of_calling_github(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(missing)
    async with connect() as c:
        r = await c.call_tool("list_recent_commits", {"repository": REPO})
    assert r.is_error and "GitHub is not configured" in r.content[0].text  # type: ignore[union-attr]
    assert not seen  # no request reached GitHub


def test_server_module_starts_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib

    monkeypatch.delenv("GITHUB_TOKEN")
    monkeypatch.delenv("GITHUB_ALLOWED_REPOS")
    importlib.reload(gh)
    assert gh.mcp is not None
