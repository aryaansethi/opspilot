"""Read-only GitHub MCP server.

Talks to the GitHub REST API with a fine-grained, read-only token. The token is
read from the environment of THIS process only; it never reaches the OpsPilot
backend, the database, or the language model.

Run: uv run --env-file .env python -m mcp_servers.github.server   (streamable HTTP on :8102/mcp)

Environment:
  GITHUB_TOKEN           fine-grained PAT: Contents, Metadata, Pull requests = read-only
  GITHUB_ALLOWED_REPOS   comma-separated "owner/name" list (exact, case-insensitive)
  GITHUB_API_URL         default https://api.github.com
"""

import asyncio
import os
import re
from datetime import datetime
from typing import Annotated, Any, Literal

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

MAX_FILES = 50
MAX_PATCH_CHARS = 4000
MAX_BODY_CHARS = 4000
REPO_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"
SHA_PATTERN = r"^[0-9a-fA-F]{7,40}$"

mcp = MCPServer(
    name="opspilot-github",
    instructions="Read-only GitHub access limited to allowlisted repositories.",
)

Repo = Annotated[str, Field(pattern=REPO_PATTERN, description="owner/name")]


class ToolInputError(ToolError):
    """Rejected input; the message is returned to the caller."""


class EmptyRepository(ToolInputError):
    """GitHub returns 409 for git operations on a repository with no commits."""


_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Test hook: route requests to a mock transport."""
    global _transport
    _transport = transport


def _client() -> httpx.AsyncClient:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "opspilot-mcp-github",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.AsyncClient(
        base_url=os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        headers=headers,
        timeout=15,
        transport=_transport,
    )


NOT_CONFIGURED = (
    "GitHub is not configured: set GITHUB_TOKEN and GITHUB_ALLOWED_REPOS in backend/.env "
    "(read only by the GitHub MCP server). OpsPilot works without GitHub; investigations skip it."
)


def _check_repo(repository: str) -> str:
    # The server starts without credentials so the rest of the stack runs on demo data;
    # every tool call then fails fast with a clear message instead of a GitHub 401.
    allowed = {
        r.strip().lower()
        for r in os.environ.get("GITHUB_ALLOWED_REPOS", "").split(",")
        if r.strip()
    }
    if not os.environ.get("GITHUB_TOKEN", "").strip() or not allowed:
        raise ToolInputError(NOT_CONFIGURED)
    if repository.lower() not in allowed:
        raise ToolInputError(f"Repository '{repository}' is not allowlisted for this integration")
    return repository


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        async with _client() as c:
            r = await c.get(path, params=params)
    except httpx.TimeoutException:
        raise ToolInputError("GitHub did not respond in time; try again later.") from None
    except httpx.TransportError as e:
        raise ToolInputError(f"GitHub is unreachable ({type(e).__name__}).") from None
    if r.status_code == 401:
        raise ToolInputError("GitHub rejected the token (401). Check GITHUB_TOKEN.")
    if r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0":
        raise ToolInputError("GitHub API rate limit reached; try again later.")
    if r.status_code in (403, 404):
        raise ToolInputError(
            f"GitHub returned {r.status_code}: repository or object not found, or token lacks access."
        )
    if r.status_code == 409:
        raise EmptyRepository("Repository is empty (it has no commits yet).")
    if r.status_code == 422:
        raise ToolInputError(
            f"GitHub rejected the request: {r.json().get('message', 'invalid input')}"
        )
    if r.status_code >= 500:
        raise ToolInputError(
            f"GitHub returned {r.status_code} (a temporary GitHub error); try again later."
        )
    if r.status_code >= 400:
        raise ToolInputError(f"GitHub returned an unexpected status {r.status_code}.")
    try:
        return r.json()
    except ValueError:
        raise ToolInputError("GitHub returned a response that is not valid JSON.") from None


def _iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ToolInputError(f"Invalid ISO-8601 timestamp: {value}") from None
    if dt.tzinfo is None:
        raise ToolInputError("Timestamps must include a timezone (e.g. 2026-11-13T09:00:00Z)")
    return dt.isoformat().replace("+00:00", "Z")


def _commit_summary(c: dict[str, Any], repository: str) -> dict[str, Any]:
    commit = c.get("commit", {})
    author = commit.get("author") or {}
    return {
        "sha": c["sha"],
        "short_sha": c["sha"][:7],
        "message": (commit.get("message") or "")[:1000],
        "author": author.get("name"),
        "authored_at": author.get("date"),
        "url": c.get("html_url") or f"https://github.com/{repository}/commit/{c['sha']}",
    }


def _files(files: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    out = [
        {
            "filename": f["filename"],
            "status": f.get("status"),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "patch": (f.get("patch") or "")[:MAX_PATCH_CHARS],
            "patch_truncated": len(f.get("patch") or "") > MAX_PATCH_CHARS,
        }
        for f in files[:MAX_FILES]
    ]
    return out, len(files) > MAX_FILES


@mcp.tool(
    description="List recent commits on a branch of an allowlisted repository, optionally within a time window or for one path."
)
async def list_recent_commits(
    repository: Repo,
    since: str | None = None,
    until: str | None = None,
    branch: Annotated[str | None, Field(max_length=255)] = None,
    path: Annotated[str | None, Field(max_length=512)] = None,
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    _check_repo(repository)
    params: dict[str, Any] = {"per_page": limit}
    if since:
        params["since"] = _iso(since)
    if until:
        params["until"] = _iso(until)
    if branch:
        params["sha"] = branch
    if path:
        params["path"] = path
    try:
        data = await _get(f"/repos/{repository}/commits", params)
    except EmptyRepository:
        return {"repository": repository, "commits": [], "note": "Repository has no commits yet."}
    return {
        "repository": repository,
        "commits": [_commit_summary(c, repository) for c in data[:limit]],
    }


@mcp.tool(description="Get one commit with changed files and (truncated) diffs.")
async def get_commit_details(
    repository: Repo, sha: Annotated[str, Field(pattern=SHA_PATTERN)]
) -> dict[str, Any]:
    _check_repo(repository)
    c = await _get(f"/repos/{repository}/commits/{sha}")
    files, more = _files(c.get("files", []))
    return {
        "repository": repository,
        **_commit_summary(c, repository),
        "stats": c.get("stats", {}),
        "files": files,
        "files_truncated": more,
    }


@mcp.tool(description="List pull requests of an allowlisted repository.")
async def list_pull_requests(
    repository: Repo,
    state: Literal["open", "closed", "all"] = "all",
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> dict[str, Any]:
    _check_repo(repository)
    data = await _get(
        f"/repos/{repository}/pulls",
        {"state": state, "per_page": limit, "sort": "updated", "direction": "desc"},
    )
    return {
        "repository": repository,
        "pull_requests": [
            {
                "number": p["number"],
                "title": p["title"],
                "state": p["state"],
                "merged_at": p.get("merged_at"),
                "author": (p.get("user") or {}).get("login"),
                "updated_at": p.get("updated_at"),
                "url": p.get("html_url"),
            }
            for p in data[:limit]
        ],
    }


@mcp.tool(description="Get one pull request with its description and changed files.")
async def get_pull_request(repository: Repo, number: Annotated[int, Field(ge=1)]) -> dict[str, Any]:
    _check_repo(repository)
    pr, files = await asyncio.gather(
        _get(f"/repos/{repository}/pulls/{number}"),
        _get(f"/repos/{repository}/pulls/{number}/files", {"per_page": 100}),
    )
    file_list, more = _files(files)
    return {
        "repository": repository,
        "number": pr["number"],
        "title": pr["title"],
        "state": pr["state"],
        "body": (pr.get("body") or "")[:MAX_BODY_CHARS],
        "author": (pr.get("user") or {}).get("login"),
        "created_at": pr.get("created_at"),
        "merged_at": pr.get("merged_at"),
        "merge_commit_sha": pr.get("merge_commit_sha"),
        "url": pr.get("html_url"),
        "files": file_list,
        "files_truncated": more,
    }


_QUALIFIER = re.compile(r"\b(repo|org|user):\S+", re.I)


@mcp.tool(description="Search code in one allowlisted repository (GitHub code search).")
async def search_code(
    repository: Repo,
    query: Annotated[str, Field(min_length=1, max_length=200)],
    limit: Annotated[int, Field(ge=1, le=30)] = 10,
) -> dict[str, Any]:
    _check_repo(repository)
    # Strip any scope qualifiers the caller added so the search can't escape the repository.
    q = _QUALIFIER.sub("", query).strip()
    if not q:
        raise ToolInputError("Query is empty after removing scope qualifiers")
    data = await _get("/search/code", {"q": f"{q} repo:{repository}", "per_page": limit})
    return {
        "repository": repository,
        "query": q,
        "total_count": data.get("total_count", 0),
        "results": [
            {"path": i["path"], "url": i.get("html_url"), "sha": i.get("sha")}
            for i in data.get("items", [])[:limit]
        ],
    }


def main() -> None:
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8102"))
    asyncio.run(mcp.run_streamable_http_async(host=host, port=port))


if __name__ == "__main__":
    main()
