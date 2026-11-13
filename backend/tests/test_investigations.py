"""End-to-end investigation workflow: state machine, evidence, analysis validation, report,
SSE replay, approvals, audit, and failure handling. Uses a scripted fake LLM, the real
CloudWatch MCP server (in-process, LocalStack synthetic incident) and a fake GitHub server."""

import asyncio
import importlib.util
import os
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from mcp.server.mcpserver import MCPServer

os.environ.setdefault("CW_ALLOWED_LOG_GROUPS", "/ecs/orders-api")
os.environ.setdefault("CW_ALLOWED_NAMESPACES", "OpsPilot/OrdersApi")

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.investigations.engine import run_investigation  # noqa: E402
from app.mcp.connection import override_server  # noqa: E402
from app.rag.embeddings.provider import HashingEmbeddings  # noqa: E402
from mcp_servers.cloudwatch.server import mcp as cloudwatch_mcp  # noqa: E402
from tests.conftest import register  # noqa: E402
from tests.test_documents import drain_and_ingest, upload, ws_headers  # noqa: E402

API = "/api/v1"
REPO = "acme/orders-api"
SHA = "b" * 40

github = MCPServer(name="fake-github-inv")
github_broken = MCPServer(name="fake-github-broken")


@github.tool()
async def list_recent_commits(
    repository: str, since: str | None = None, until: str | None = None, limit: int = 10
) -> dict[str, Any]:
    return {
        "repository": repository,
        "commits": [
            {
                "sha": SHA,
                "short_sha": SHA[:7],
                "message": "Release 4.3: set hikari maximum-pool-size to 10",
                "author": "dev",
                "authored_at": (datetime.now(UTC) - timedelta(minutes=61)).isoformat(),
                "url": "https://github.com/x",
            }
        ],
    }


@github.tool()
async def get_commit_details(repository: str, sha: str) -> dict[str, Any]:
    return {
        "repository": repository,
        "sha": sha,
        "short_sha": sha[:7],
        "message": "Release 4.3",
        "url": "https://github.com/x",
        "files": [
            {
                "filename": "application.yml",
                "additions": 1,
                "deletions": 1,
                "patch": "-maximum-pool-size: 50\n+maximum-pool-size: 10",
            }
        ],
    }


@github_broken.tool(name="list_recent_commits")
async def broken_list_recent_commits(
    repository: str, since: str | None = None, until: str | None = None, limit: int = 10
) -> dict[str, Any]:
    raise RuntimeError("GitHub is down")


RUNBOOK = b"""# Orders API Runbook

## Database connection exhaustion

ERR_POOL_TIMEOUT means the HikariCP pool is exhausted. Compare maximum-pool-size with the previous release.
"""
INCIDENT = b"""# INC-2026-031 Checkout timeouts

## Root cause

Release 4.2 reduced the connection pool from 50 to 10. Rolling back fixed latency.
"""


class ScriptedLLM:
    """Plans every task; analysis cites real labels found in the prompt, plus junk to be filtered."""

    model = "scripted"

    def __init__(self, *, plan: Any = None, analysis: Any = None, delay: float = 0.0) -> None:
        self.plan, self.analysis, self.delay = plan, analysis, delay
        self.calls: list[str] = []
        self.prompts: dict[str, str] = {}

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        self.calls.append(schema_name)
        self.prompts[schema_name] = user
        if self.delay:
            await asyncio.sleep(self.delay)
        if schema_name == "investigation_plan":
            if isinstance(self.plan, Exception):
                raise self.plan
            return self.plan or {
                "incident_type": "db_connection",
                "tasks": [
                    "search_runbooks",
                    "check_cloudwatch_alarms",
                    "query_cloudwatch_logs",
                    "query_cloudwatch_metrics",
                    "search_recent_github_commits",
                    "delete_everything",
                ],
                "log_search_terms": ["ERR_POOL_TIMEOUT", "rm -rf /"],
                "rationale": "pool errors",
            }
        if isinstance(self.analysis, Exception):
            raise self.analysis
        if self.analysis is not None:
            return self.analysis
        labels = dict(re.findall(r'<evidence label="(E\d+)" source="(\w+)"', user))
        cw = next(lbl for lbl, src in labels.items() if src == "cloudwatch")
        kb = next(lbl for lbl, src in labels.items() if src == "knowledge_base")
        return {
            "overview": "Latency rose after a deploy that reduced the pool.",
            "observed_facts": [
                {"text": "ERROR pool timeouts appear in the window", "evidence": [cw]},
                {"text": "Made-up fact", "evidence": ["E99"]},
            ],
            "hypotheses": [
                {
                    "statement": "The root cause is the pool size reduction",
                    "supporting": [cw, kb],
                    "contradicting": [],
                    "missing_evidence": ["pool utilisation before deploy"],
                    "confidence_explanation": "Timing and config line up",
                    "validation_steps": ["Compare maximum-pool-size with release 4.2"],
                },
                {
                    "statement": "Unsupported guess",
                    "supporting": ["E77"],
                    "contradicting": [],
                    "missing_evidence": [],
                    "confidence_explanation": "none",
                    "validation_steps": [],
                },
            ],
            "recommended_diagnostics": ["Check hikaricp.connections.active"],
            "proposed_remediation": ["Roll back the pool configuration"],
            "unknowns": ["Database-side metrics were not available"],
        }


@pytest.fixture(scope="module", autouse=True)
def seeded() -> None:
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_cloudwatch.py"
    spec = importlib.util.spec_from_file_location("seed_cloudwatch", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


@pytest.fixture(autouse=True)
def servers() -> Iterator[None]:
    override_server("cloudwatch", cloudwatch_mcp)
    override_server("github", github)
    yield
    override_server("cloudwatch", None)
    override_server("github", None)


def window() -> dict[str, str]:
    end = datetime.now(UTC) + timedelta(minutes=1)
    return {"time_start": (end - timedelta(hours=3)).isoformat(), "time_end": end.isoformat()}


async def workspace(
    client: AsyncClient,
    *,
    integrations: tuple[str, ...] = ("cloudwatch", "github"),
    docs: bool = True,
) -> dict[str, Any]:
    u = await register(client)
    h = ws_headers(u)
    await client.post(f"{API}/tools/sync", headers=h)
    configs = {
        "cloudwatch": {"log_groups": ["/ecs/orders-api"], "namespaces": ["OpsPilot/OrdersApi"]},
        "github": {"repositories": [REPO]},
    }
    for kind in integrations:
        assert (
            await client.post(
                f"{API}/integrations", headers=h, json={"kind": kind, "config": configs[kind]}
            )
        ).status_code == 201
    if docs:
        await upload(client, u, RUNBOOK, "runbook.md")
        r = await client.post(
            f"{API}/documents/upload-url",
            headers=h,
            json={
                "filename": "inc.md",
                "mime_type": "text/markdown",
                "size_bytes": len(INCIDENT),
                "source_type": "incident_report",
            },
        )
        import httpx

        async with httpx.AsyncClient() as raw:
            await raw.put(r.json()["upload_url"], content=INCIDENT, headers=r.json()["headers"])
        await client.post(
            f"{API}/documents/complete-upload",
            headers=h,
            json={"document_id": r.json()["document_id"]},
        )
        await drain_and_ingest()
    return {**u, "h": h}


async def start(client: AsyncClient, h: dict[str, str], **body: Any) -> str:
    r = await client.post(
        f"{API}/investigations",
        headers=h,
        json={"question": "Why did orders-api latency increase after the deploy?", **body},
    )
    assert r.status_code == 202, r.text
    return str(r.json()["id"])


async def run(inv_id: str, llm: Any) -> str:
    async with get_sessionmaker()() as db:
        return await run_investigation(db, uuid.UUID(inv_id), llm=llm, embedder=HashingEmbeddings())


async def test_full_investigation_produces_validated_report(client: AsyncClient) -> None:
    u = await workspace(client)
    inv_id = await start(client, u["h"], service="orders-api", environment="production", **window())
    llm = ScriptedLLM()
    assert await run(inv_id, llm) == "COMPLETED"
    assert llm.calls == ["investigation_plan", "investigation_analysis"]

    inv = (await client.get(f"{API}/investigations/{inv_id}", headers=u["h"])).json()
    assert inv["state"] == "COMPLETED" and inv["incident_type"] == "db_connection"
    assert "delete_everything" not in inv["plan"]["tasks"]  # invalid task dropped
    assert inv["plan"]["log_search_terms"] == ["ERR_POOL_TIMEOUT"]  # unsafe term dropped

    evidence = (await client.get(f"{API}/investigations/{inv_id}/evidence", headers=u["h"])).json()
    systems = {e["source_system"] for e in evidence}
    assert systems == {"knowledge_base", "cloudwatch", "github"}
    titles = " | ".join(e["title"] for e in evidence)
    assert (
        "ERROR log events in /ecs/orders-api" in titles
        and "Alarm orders-api-p95-latency is ALARM" in titles
    )
    assert any(
        "maximum-pool-size=10" in e["excerpt"] for e in evidence
    )  # config change found in logs
    metric = next(
        e for e in evidence if e["title"].startswith("Metric OpsPilot/OrdersApi/LatencyP95")
    )
    assert (
        "First point at least 2x or at most 0.5x the baseline" in metric["excerpt"]
        and "Recent (mean of last" in metric["excerpt"]
    )
    assert any("+maximum-pool-size: 10" in e["excerpt"] for e in evidence)  # github diff

    hyps = (await client.get(f"{API}/investigations/{inv_id}/hypotheses", headers=u["h"])).json()
    assert len(hyps) == 1  # unsupported one dropped
    assert hyps[0]["status"] == "supported" and "root cause" not in hyps[0]["statement"].lower()
    ids = {e["id"] for e in evidence}
    assert set(hyps[0]["supporting_evidence_ids"]) <= ids

    rep = (await client.get(f"{API}/investigations/{inv_id}/report", headers=u["h"])).json()
    assert len(rep["observed_facts"]) == 1  # E99 fact dropped
    assert any("removed because they cited no valid" in x for x in rep["unknowns"])
    assert rep["tool_summary"]["total"] >= 6 and rep["tool_summary"]["failed"] == 0
    assert "## Hypotheses (not confirmed)" in rep["markdown"]
    # prompts carry evidence as labelled data
    assert '<evidence label="E1"' in llm.prompts["investigation_analysis"]

    calls = (await client.get(f"{API}/investigations/{inv_id}/tool-calls", headers=u["h"])).json()
    assert calls and all(c["access"] == "read" for c in calls)
    assert len(calls) <= get_settings().investigation_max_tool_calls


async def test_missing_parameters_then_continue(client: AsyncClient) -> None:
    u = await workspace(client, integrations=("cloudwatch",))
    inv_id = await start(client, u["h"])
    assert await run(inv_id, ScriptedLLM()) == "AWAITING_PARAMETERS"
    inv = (await client.get(f"{API}/investigations/{inv_id}", headers=u["h"])).json()
    assert inv["missing_parameters"] == ["service", "time_range"]
    bad = await client.post(
        f"{API}/investigations/{inv_id}/continue",
        headers=u["h"],
        json={
            "service": "orders-api",
            "time_start": "2026-01-01T00:00:00Z",
            "time_end": "2026-01-03T00:00:00Z",
        },
    )
    assert bad.status_code == 400 and "24 hours" in bad.json()["error"]["message"]
    ok = await client.post(
        f"{API}/investigations/{inv_id}/continue",
        headers=u["h"],
        json={"service": "orders-api", **window()},
    )
    assert ok.status_code == 200 and ok.json()["state"] == "RECEIVED"
    assert await run(inv_id, ScriptedLLM()) == "COMPLETED"
    again = await client.post(
        f"{API}/investigations/{inv_id}/continue", headers=u["h"], json={"service": "x"}
    )
    assert again.status_code == 409


async def test_sse_replay_respects_last_event_id(client: AsyncClient) -> None:
    u = await workspace(client, integrations=("cloudwatch",), docs=False)
    inv_id = await start(client, u["h"], service="orders-api", **window())
    await run(
        inv_id,
        ScriptedLLM(
            analysis={
                "overview": "x",
                "observed_facts": [],
                "hypotheses": [],
                "recommended_diagnostics": [],
                "proposed_remediation": [],
                "unknowns": [],
            }
        ),
    )
    r = await client.get(f"{API}/investigations/{inv_id}/events?follow=false", headers=u["h"])
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = [f for f in r.text.split("\n\n") if f.strip()]
    seqs = [int(re.search(r"^id: (\d+)", f, re.M).group(1)) for f in frames]  # type: ignore[union-attr]
    assert seqs == list(range(1, len(seqs) + 1))
    types = [re.search(r"^event: (\w+)", f, re.M).group(1) for f in frames]  # type: ignore[union-attr]
    assert (
        "report_ready" in types and "tool_call_completed" in types and types[-1] == "state_changed"
    )
    r2 = await client.get(
        f"{API}/investigations/{inv_id}/events?follow=false",
        headers={**u["h"], "Last-Event-ID": str(seqs[-3])},
    )
    assert len([f for f in r2.text.split("\n\n") if f.strip()]) == 2


async def test_live_stream_delivers_new_events() -> None:
    """The follow=True path: LISTEN/NOTIFY wakes the stream when a new event is committed."""
    from app.investigations import events as ev
    from app.models import Investigation, User, Workspace

    async with get_sessionmaker()() as db:
        user = User(
            email=f"sse-{uuid.uuid4().hex[:6]}@example.com", password_hash="x", display_name="s"
        )
        ws = Workspace(name="sse", slug=f"sse-{uuid.uuid4().hex[:6]}")
        db.add_all([user, ws])
        await db.flush()
        inv = Investigation(
            workspace_id=ws.id, created_by=user.id, question="live?", state="RECEIVED"
        )
        db.add(inv)
        await db.commit()
        inv_id, ws_id = inv.id, ws.id

    received: list[str] = []

    async def reader() -> None:
        async with get_sessionmaker()() as db:
            async for frame in ev.stream(db, inv_id, 0, keepalive_seconds=0.2, max_seconds=5):
                if frame.startswith("id:"):
                    received.append(frame)
                    if len(received) == 2:
                        return

    task = asyncio.create_task(reader())
    await asyncio.sleep(0.5)
    async with get_sessionmaker()() as db:
        inv = await db.get(Investigation, inv_id)
        assert inv is not None
        await ev.emit(db, inv, "step_started", {"step": "a"})
        await ev.emit(db, inv, "step_completed", {"step": "a"})
    await asyncio.wait_for(task, 5)
    assert "event: step_started" in received[0] and "event: step_completed" in received[1]
    assert ws_id


async def test_plan_failure_falls_back_and_tool_failure_is_partial(client: AsyncClient) -> None:
    override_server("github", github_broken)
    u = await workspace(client)
    inv_id = await start(client, u["h"], service="orders-api", **window())
    assert await run(inv_id, ScriptedLLM(plan=RuntimeError("bad json"))) == "PARTIAL"
    inv = (await client.get(f"{API}/investigations/{inv_id}", headers=u["h"])).json()
    assert inv["plan"]["source"] == "default"
    joined = " ".join(inv["failed_steps"])
    assert "default plan used" in joined and "github.list_recent_commits failed" in joined
    rep = (await client.get(f"{API}/investigations/{inv_id}/report", headers=u["h"])).json()
    assert rep["tool_summary"]["failed"] >= 1


async def test_analysis_failure_keeps_evidence(client: AsyncClient) -> None:
    u = await workspace(client, integrations=("cloudwatch",), docs=False)
    inv_id = await start(client, u["h"], service="orders-api", **window())
    assert await run(inv_id, ScriptedLLM(analysis=RuntimeError("model crashed"))) == "FAILED_LLM"
    assert (await client.get(f"{API}/investigations/{inv_id}/evidence", headers=u["h"])).json()
    rep = (await client.get(f"{API}/investigations/{inv_id}/report", headers=u["h"])).json()
    assert rep["hypotheses"] == [] and "did not complete" in rep["overview"]


async def test_no_evidence_skips_analysis(client: AsyncClient) -> None:
    u = await workspace(client, integrations=(), docs=False)
    inv_id = await start(client, u["h"], service="orders-api", **window())
    llm = ScriptedLLM()
    assert await run(inv_id, llm) == "COMPLETED"
    assert llm.calls == ["investigation_plan"]
    rep = (await client.get(f"{API}/investigations/{inv_id}/report", headers=u["h"])).json()
    assert "No relevant evidence" in rep["overview"]


async def test_timeout_stops_run(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    u = await workspace(client, integrations=(), docs=False)
    inv_id = await start(client, u["h"], service="orders-api", **window())
    monkeypatch.setattr(get_settings(), "investigation_timeout_seconds", 1)
    assert await run(inv_id, ScriptedLLM(delay=3)) == "PARTIAL"
    inv = (await client.get(f"{API}/investigations/{inv_id}", headers=u["h"])).json()
    assert "timeout" in inv["failed_steps"] and "exceeded" in inv["error"]


async def test_workspace_tool_switch_blocks_tool(client: AsyncClient) -> None:
    u = await workspace(client, integrations=("cloudwatch",), docs=False)
    integ = (await client.get(f"{API}/integrations", headers=u["h"])).json()[0]
    r = await client.patch(
        f"{API}/integrations/{integ['id']}/tools/describe_alarms",
        headers=u["h"],
        json={"enabled": False},
    )
    assert r.status_code == 200
    assert next(t for t in r.json()["tools"] if t["name"] == "describe_alarms")["enabled"] is False
    inv_id = await start(client, u["h"], service="orders-api", **window())
    await run(inv_id, ScriptedLLM())
    inv = (await client.get(f"{API}/investigations/{inv_id}", headers=u["h"])).json()
    assert any(
        "describe_alarms unavailable" in s and "disabled for this workspace" in s
        for s in inv["failed_steps"]
    )
    unknown = await client.patch(
        f"{API}/integrations/{integ['id']}/tools/nope", headers=u["h"], json={"enabled": False}
    )
    assert unknown.status_code == 404


async def test_approval_flow_never_executes_without_jira(client: AsyncClient) -> None:
    u = await workspace(client, integrations=("cloudwatch",), docs=False)
    inv_id = await start(client, u["h"], service="orders-api", **window())
    fields = {
        "project": "OPS",
        "issue_type": "Incident",
        "summary": "Orders latency",
        "description": "See report",
        "labels": ["sev2"],
    }
    early = await client.post(
        f"{API}/investigations/{inv_id}/actions",
        headers=u["h"],
        json={"kind": "create_jira_issue", "fields": fields},
    )
    assert early.status_code == 409
    await run(inv_id, ScriptedLLM())
    a = (
        await client.post(
            f"{API}/investigations/{inv_id}/actions",
            headers=u["h"],
            json={"kind": "create_jira_issue", "fields": fields},
        )
    ).json()
    assert (
        a["status"] == "pending"
        and a["arguments"] == fields
        and a["requested_by"]["email"] == "alice@example.com"
    )
    pending = (await client.get(f"{API}/approvals?status=pending", headers=u["h"])).json()
    assert [p["id"] for p in pending] == [a["id"]]
    done = (await client.post(f"{API}/approvals/{a['id']}/approve", headers=u["h"])).json()
    assert done["status"] == "failed" and "not registered" in done["error"]
    assert (
        await client.post(f"{API}/approvals/{a['id']}/approve", headers=u["h"])
    ).status_code == 409
    b = (
        await client.post(
            f"{API}/investigations/{inv_id}/actions",
            headers=u["h"],
            json={"kind": "create_jira_issue", "fields": fields},
        )
    ).json()
    rejected = (await client.post(f"{API}/approvals/{b['id']}/reject", headers=u["h"])).json()
    assert (
        rejected["status"] == "rejected" and rejected["decided_by"]["email"] == "alice@example.com"
    )
    bad = await client.post(
        f"{API}/investigations/{inv_id}/actions",
        headers=u["h"],
        json={"kind": "create_jira_issue", "fields": {**fields, "project": "OPS; DROP"}},
    )
    assert bad.status_code == 422
    audit = (await client.get(f"{API}/audit-events?action=approval", headers=u["h"])).json()
    actions = [x["action"] for x in audit["items"]]
    assert {
        "approval.requested",
        "approval.approved",
        "approval.failed",
        "approval.rejected",
    } <= set(actions)
    assert audit["items"][0]["actor"]["email"] == "alice@example.com"


async def test_isolation_and_validation(client: AsyncClient) -> None:
    alice = await workspace(client, integrations=(), docs=False)
    inv_id = await start(client, alice["h"], service="orders-api", **window())
    eve = await register(client, "eve@example.com")
    for path in (
        "",
        "/evidence",
        "/hypotheses",
        "/tool-calls",
        "/report",
        "/approvals",
        "/events?follow=false",
    ):
        assert (
            await client.get(f"{API}/investigations/{inv_id}{path}", headers=ws_headers(eve))
        ).status_code == 404
    assert (await client.get(f"{API}/investigations", headers=ws_headers(eve))).json()[
        "items"
    ] == []
    too_long = await client.post(
        f"{API}/investigations",
        headers=alice["h"],
        json={
            "question": "Why is it slow?",
            "time_start": "2026-01-01T00:00:00Z",
            "time_end": "2026-01-03T00:00:00Z",
        },
    )
    assert too_long.status_code == 400
    half = await client.post(
        f"{API}/investigations",
        headers=alice["h"],
        json={"question": "Why is it slow?", "time_start": "2026-01-01T00:00:00Z"},
    )
    assert half.status_code == 400
    listing = (await client.get(f"{API}/investigations?limit=1", headers=alice["h"])).json()
    assert (
        listing["items"][0]["id"] == inv_id
        and listing["items"][0]["created_by"]["email"] == "alice@example.com"
    )


async def test_crashing_collector_is_contained(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.investigations.collectors import Collector

    async def boom(self: Collector) -> None:
        raise RuntimeError("collector bug")

    monkeypatch.setattr(Collector, "metrics", boom)
    u = await workspace(client, integrations=("cloudwatch",))
    inv_id = await start(client, u["h"], service="orders-api", **window())
    assert await run(inv_id, ScriptedLLM()) == "PARTIAL"
    inv = (await client.get(f"{API}/investigations/{inv_id}", headers=u["h"])).json()
    assert "query_cloudwatch_metrics: RuntimeError" in inv["failed_steps"]
    # the other sources still produced evidence and a report
    assert (await client.get(f"{API}/investigations/{inv_id}/evidence", headers=u["h"])).json()
    assert (
        await client.get(f"{API}/investigations/{inv_id}/report", headers=u["h"])
    ).status_code == 200


def test_numeric_grounding_drops_invented_numbers() -> None:
    from app.investigations.analysis import EvidenceRef, ungrounded_numbers, validate_analysis

    ev = [
        EvidenceRef(
            "id1",
            "E1",
            "knowledge_base",
            "INC",
            "Date: 2026-03-14. Pool reduced from 50 to 10. p95 rose to 2.4 s.",
        )
    ]
    assert ungrounded_numbers("Pool went from 50 to 10 on 2026-03-14", [ev[0].excerpt]) == []
    assert ungrounded_numbers("Incident on 2026-11-06 with 12.3k errors", [ev[0].excerpt]) == [
        "2026-11-06",
        "12.3",
    ]
    out = validate_analysis(
        {
            "overview": "o",
            "recommended_diagnostics": [],
            "proposed_remediation": [],
            "unknowns": [],
            "observed_facts": [
                {"text": "Pool reduced from 50 to 10", "evidence": ["E1"]},
                {"text": "Previous incident on 2026-11-06", "evidence": ["E1"]},
            ],
            "hypotheses": [
                {
                    "statement": "Pool size 50 to 10 caused it",
                    "supporting": ["E1"],
                    "contradicting": [],
                    "missing_evidence": [],
                    "confidence_explanation": "",
                    "validation_steps": [],
                },
                {
                    "statement": "Errors hit 12.3k per minute",
                    "supporting": ["E1"],
                    "contradicting": [],
                    "missing_evidence": [],
                    "confidence_explanation": "",
                    "validation_steps": [],
                },
            ],
        },
        ev,
    )
    assert [f["text"] for f in out.facts] == ["Pool reduced from 50 to 10"]
    assert [h.statement for h in out.hypotheses] == ["Pool size 50 to 10 caused it"]
    assert out.dropped["ungrounded_numbers"] == 2
    assert any("numbers or dates not found" in u for u in out.unknowns)


def test_docs_only_support_is_never_supported_and_schema_keys_are_dropped() -> None:
    from app.investigations.analysis import EvidenceRef, analysis_prompt, validate_analysis

    ev = [
        EvidenceRef("kb", "E1", "knowledge_base", "Runbook", "Third-party APIs can add latency."),
        EvidenceRef("cw", "E2", "cloudwatch", "Logs", "ERROR HikariPool timeout"),
    ]
    hyp = {
        "contradicting": [],
        "missing_evidence": ["missing_evidence", "Vendor status page"],
        "confidence_explanation": "",
        "validation_steps": ["remediation_steps", "Check vendor latency"],
    }
    out = validate_analysis(
        {
            "overview": "",
            "observed_facts": [],
            "recommended_diagnostics": ["recommended_diagnostics"],
            "proposed_remediation": [],
            "unknowns": [],
            "hypotheses": [
                {
                    "statement": "A third-party dependency added latency",
                    "supporting": ["E1"],
                    **hyp,
                },
                {"statement": "Pool exhaustion", "supporting": ["E2", "E1"], **hyp},
            ],
        },
        ev,
    )
    assert [h.status for h in out.hypotheses] == ["proposed", "supported"]
    assert out.hypotheses[0].validation_steps == ["Check vendor latency"]
    assert out.hypotheses[0].missing_evidence == ["Vendor status page"]
    assert out.diagnostics == []
    prompt = analysis_prompt("q", "s", ev)
    assert 'label="E1" source="knowledge_base" kind="documentation"' in prompt
    assert 'label="E2" source="cloudwatch" kind="live"' in prompt


async def test_docs_only_run_is_flagged(client: AsyncClient) -> None:
    u = await workspace(client, integrations=())
    inv_id = await start(client, u["h"], service="orders-api", **window())
    analysis = {
        "overview": "o",
        "observed_facts": [],
        "recommended_diagnostics": [],
        "proposed_remediation": [],
        "unknowns": [],
        "hypotheses": [
            {
                "statement": "Pool size reduction",
                "supporting": ["E1"],
                "contradicting": [],
                "missing_evidence": [],
                "confidence_explanation": "",
                "validation_steps": [],
            }
        ],
    }
    assert await run(inv_id, ScriptedLLM(analysis=analysis)) == "COMPLETED"
    rep = (await client.get(f"{API}/investigations/{inv_id}/report", headers=u["h"])).json()
    assert rep["unknowns"][0].startswith("No live evidence")
    assert [h["status"] for h in rep["hypotheses"]] == ["proposed"]
