"""Evidence collectors: knowledge base (hybrid RAG) and read-only MCP tools.

Every collector writes normalised `evidence_items` (labelled E1, E2, ...) and
emits progress events. Tool calls go through `invoke_tool`, so registry,
workspace allowlists, timeouts, size caps and auditing all apply. Statistics in
metric evidence are computed here from raw datapoints and say so.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import WorkspaceCtx
from app.core.config import get_settings
from app.investigations.events import emit
from app.mcp.invoker import ToolResult, invoke_tool
from app.models import ConnectedIntegration, EvidenceItem, Investigation
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.pipeline import hybrid_search
from app.rag.reranking.reranker import default_reranker
from app.rag.types import SearchFilters

_NUM = re.compile(r"\d+")


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@dataclass
class Collector:
    db: AsyncSession
    inv: Investigation
    ctx: WorkspaceCtx
    embedder: EmbeddingProvider
    integrations: dict[str, ConnectedIntegration]
    tool_calls: int = 0
    failed_steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _query_vector: list[float] | None = None

    # ---------------------------------------------------------------- helpers
    async def add_evidence(
        self,
        *,
        source_system: str,
        title: str,
        source_reference: str,
        excerpt: str,
        url: str | None = None,
        observed_at: datetime | None = None,
        time_range: dict[str, str] | None = None,
        retrieval_method: str | None = None,
        rank: int | None = None,
        reliability_notes: str | None = None,
        tool_invocation_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EvidenceItem:
        count = await self.db.scalar(
            select(func.count())
            .select_from(EvidenceItem)
            .where(EvidenceItem.investigation_id == self.inv.id)
        )
        item = EvidenceItem(
            workspace_id=self.inv.workspace_id,
            investigation_id=self.inv.id,
            label=f"E{(count or 0) + 1}",
            source_system=source_system,
            title=title[:300],
            source_reference=source_reference[:600],
            url=url,
            excerpt=excerpt[:6000],
            observed_at=observed_at,
            time_range=time_range,
            retrieval_method=retrieval_method,
            rank=rank,
            reliability_notes=reliability_notes,
            tool_invocation_id=tool_invocation_id,
            item_metadata=metadata or {},
        )
        self.db.add(item)
        await self.db.flush()
        await emit(
            self.db,
            self.inv,
            "evidence_added",
            {
                "evidence_id": str(item.id),
                "label": item.label,
                "source_system": source_system,
                "title": item.title,
            },
        )
        return item

    def budget_left(self) -> bool:
        if self.tool_calls >= get_settings().investigation_max_tool_calls:
            note = f"Tool-call budget ({get_settings().investigation_max_tool_calls}) reached; some sources were not queried."
            if note not in self.notes:
                self.notes.append(note)
            return False
        return True

    async def call(self, tool: str, args: dict[str, Any], step: str) -> ToolResult | None:
        if not self.budget_left():
            return None
        self.tool_calls += 1
        server, name = tool.split(".", 1)
        await emit(
            self.db,
            self.inv,
            "tool_call_started",
            {"tool": tool, "server": server, "name": name, "arguments": args},
        )
        try:
            r = await invoke_tool(self.db, self.ctx, tool, args, investigation_id=self.inv.id)
        except Exception as e:  # registry / permission errors, raised before anything is written
            msg = getattr(e, "message", None) or type(e).__name__
            self.failed_steps.append(f"{step}: {tool} unavailable ({msg})")
            await emit(
                self.db,
                self.inv,
                "tool_call_completed",
                {"tool": tool, "status": "denied", "error": msg},
            )
            return None
        await emit(
            self.db,
            self.inv,
            "tool_call_completed",
            {
                "tool": tool,
                "invocation_id": str(r.invocation_id),
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error": r.error,
                "truncated": r.truncated,
            },
        )
        if r.status != "succeeded":
            self.failed_steps.append(f"{step}: {tool} {r.status} ({r.error})")
            return None
        return r

    @property
    def window(self) -> dict[str, str]:
        assert self.inv.time_start and self.inv.time_end
        return {"start_time": iso(self.inv.time_start), "end_time": iso(self.inv.time_end)}

    # ------------------------------------------------------------ knowledge
    async def knowledge(self, source_types: tuple[str, ...], top_k: int, label: str) -> None:
        query = f"{self.inv.question} {self.inv.service or ''}".strip()
        if self._query_vector is None:  # embed once, reuse for every knowledge search
            [self._query_vector] = await self.embedder.embed([query])
        out = await hybrid_search(
            self.db,
            self.inv.workspace_id,
            query,
            embedder=self.embedder,
            filters=SearchFilters(source_types=source_types),
            top_k=top_k,
            query_vector=self._query_vector,
            reranker=default_reranker(),
        )
        for rank, c in enumerate(out.results, start=1):
            loc = c.section_path or c.document_title
            await self.add_evidence(
                source_system="knowledge_base",
                title=f"{c.document_title} › {loc}" if c.section_path else c.document_title,
                source_reference=f"document:{c.document_id}#chunk:{c.chunk_id}",
                excerpt=c.content,
                retrieval_method="hybrid_rrf",
                rank=rank,
                reliability_notes=f"Indexed {c.source_type.replace('_', ' ')}; may be outdated.",
                metadata={
                    "document_id": str(c.document_id),
                    "chunk_id": str(c.chunk_id),
                    "section_path": c.section_path,
                    "page_start": c.page_start,
                    "source_type": c.source_type,
                    "search": label,
                },
            )

    # ------------------------------------------------------------ cloudwatch
    def _cw(self) -> dict[str, Any]:
        return self.integrations["cloudwatch"].config

    async def alarms(self) -> None:
        r = await self.call(
            "cloudwatch.describe_alarms", {"state": "ALARM"}, "check_cloudwatch_alarms"
        )
        if not r or not r.data:
            return
        for a in r.data.get("alarms", [])[:3]:
            await self.add_evidence(
                source_system="cloudwatch",
                title=f"Alarm {a['name']} is {a['state']}",
                source_reference=f"cloudwatch:alarm:{a['name']}",
                excerpt=(
                    f"Alarm {a['name']} state={a['state']} since {a.get('updated_at')}. Metric {a.get('namespace')}/"
                    f"{a.get('metric')} {a.get('comparison')} {a.get('threshold')}. Reason: {a.get('reason')}"
                ),
                observed_at=_parse(a.get("updated_at")),
                retrieval_method="describe_alarms",
                tool_invocation_id=r.invocation_id,
                metadata={"alarm": a},
            )

    async def logs(self, terms: list[str]) -> None:
        for group in self._cw().get("log_groups", [])[:2]:
            r = await self.call(
                "cloudwatch.filter_log_events",
                {"log_group": group, "filter_pattern": "ERROR", "limit": 200, **self.window},
                "query_cloudwatch_logs",
            )
            if r and r.data:
                events = r.data.get("events", [])
                if events:
                    templates = Counter(_NUM.sub("N", e["message"])[:200] for e in events)
                    lines = [f"{n}× {t}" for t, n in templates.most_common(5)]
                    more = " (more exist; result truncated)" if r.data.get("truncated") else ""
                    await self.add_evidence(
                        source_system="cloudwatch",
                        title=f"{len(events)} ERROR log events in {group}{more}",
                        source_reference=f"cloudwatch:logs:{group}?filter=ERROR",
                        excerpt=(
                            f"Log group {group}, window {self.window['start_time']} to {self.window['end_time']}.\n"
                            f"ERROR events returned: {len(events)}{more}. First: {events[0]['timestamp']}. "
                            f"Last: {events[-1]['timestamp']}.\nMost common messages (numbers replaced by N):\n"
                            + "\n".join(lines)
                        ),
                        observed_at=_parse(events[0]["timestamp"]),
                        time_range={
                            "start": events[0]["timestamp"],
                            "end": events[-1]["timestamp"],
                        },
                        retrieval_method="filter_log_events",
                        tool_invocation_id=r.invocation_id,
                        reliability_notes="Counts are of returned events and are capped at 200.",
                        metadata={
                            "log_group": group,
                            "count": len(events),
                            "truncated": r.data.get("truncated"),
                        },
                    )
                else:
                    self.notes.append(f"No ERROR events in {group} during the window.")
            for term in terms:
                r = await self.call(
                    "cloudwatch.filter_log_events",
                    {"log_group": group, "filter_pattern": term, "limit": 20, **self.window},
                    "query_cloudwatch_logs",
                )
                if not r or not r.data or not r.data.get("events"):
                    continue
                events = r.data["events"]
                await self.add_evidence(
                    source_system="cloudwatch",
                    title=f"Log events matching '{term}' in {group}",
                    source_reference=f"cloudwatch:logs:{group}?filter={term}",
                    excerpt="\n".join(f"{e['timestamp']} {e['message']}" for e in events[:15]),
                    observed_at=_parse(events[0]["timestamp"]),
                    time_range={"start": events[0]["timestamp"], "end": events[-1]["timestamp"]},
                    retrieval_method="filter_log_events",
                    tool_invocation_id=r.invocation_id,
                    metadata={"log_group": group, "term": term, "count": len(events)},
                )

    async def metrics(self) -> None:
        assert self.inv.time_start and self.inv.time_end
        seconds = (self.inv.time_end - self.inv.time_start).total_seconds()
        period = max(60, int(seconds // 120 // 60 + 1) * 60)
        for ns in self._cw().get("namespaces", [])[:2]:
            dims = {"Service": self.inv.service} if self.inv.service else None
            r = await self.call(
                "cloudwatch.list_metrics",
                {"namespace": ns, **({"dimensions": dims} if dims else {})},
                "query_cloudwatch_metrics",
            )
            if not r or not r.data:
                continue
            found = r.data.get("metrics", [])
            if not found:
                self.notes.append(f"No metrics for service {self.inv.service} in namespace {ns}.")
            for m in found[:4]:
                res = await self.call(
                    "cloudwatch.get_metric_data",
                    {
                        "namespace": ns,
                        "metric_name": m["metric_name"],
                        "dimensions": m["dimensions"],
                        "period_seconds": period,
                        "stat": "Average",
                        **self.window,
                    },
                    "query_cloudwatch_metrics",
                )
                if not res or not res.data:
                    continue
                pts = res.data.get("datapoints", [])
                if not pts:
                    continue
                await self.add_evidence(
                    source_system="cloudwatch",
                    title=f"Metric {ns}/{m['metric_name']} ({period}s average)",
                    source_reference=f"cloudwatch:metric:{ns}/{m['metric_name']}",
                    excerpt=_describe_series(ns, m["metric_name"], m["dimensions"], period, pts),
                    time_range={"start": pts[0]["timestamp"], "end": pts[-1]["timestamp"]},
                    retrieval_method="get_metric_data",
                    tool_invocation_id=res.invocation_id,
                    reliability_notes="Baseline, peak and change point were computed by OpsPilot from the raw datapoints.",
                    metadata={
                        "namespace": ns,
                        "metric": m["metric_name"],
                        "dimensions": m["dimensions"],
                        "points": len(pts),
                    },
                )

    # ------------------------------------------------------------ github
    async def commits(self) -> None:
        assert self.inv.time_start and self.inv.time_end
        since = iso(self.inv.time_start - timedelta(hours=24))
        until = iso(self.inv.time_end)
        for repo in self.integrations["github"].config.get("repositories", [])[:2]:
            r = await self.call(
                "github.list_recent_commits",
                {"repository": repo, "since": since, "until": until, "limit": 10},
                "search_recent_github_commits",
            )
            if not r or not r.data:
                continue
            commits = r.data.get("commits", [])
            if not commits:
                self.notes.append(f"No commits in {repo} between {since} and {until}.")
                continue
            await self.add_evidence(
                source_system="github",
                title=f"{len(commits)} commits in {repo} in the 24h before/during the window",
                source_reference=f"github:{repo}/commits?since={since}&until={until}",
                url=f"https://github.com/{repo}/commits",
                excerpt="\n".join(
                    f"{c['short_sha']} {c.get('authored_at')} {c.get('author')}: {c['message'].splitlines()[0][:120]}"
                    for c in commits
                ),
                time_range={"start": since, "end": until},
                retrieval_method="list_recent_commits",
                tool_invocation_id=r.invocation_id,
                metadata={"repository": repo, "count": len(commits)},
            )
            for c in commits[:2]:
                d = await self.call(
                    "github.get_commit_details",
                    {"repository": repo, "sha": c["sha"]},
                    "search_recent_github_commits",
                )
                if not d or not d.data:
                    continue
                files = d.data.get("files", [])
                diff = "\n".join(
                    f"--- {f['filename']} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})\n{f.get('patch', '')[:600]}"
                    for f in files[:6]
                )
                await self.add_evidence(
                    source_system="github",
                    title=f"Commit {c['short_sha']} in {repo}: {c['message'].splitlines()[0][:100]}",
                    source_reference=f"github:{repo}@{c['sha']}",
                    url=d.data.get("url") or c.get("url"),
                    excerpt=f"{c['message'][:500]}\nAuthor {c.get('author')} at {c.get('authored_at')}\n{diff}",
                    observed_at=_parse(c.get("authored_at")),
                    retrieval_method="get_commit_details",
                    tool_invocation_id=d.invocation_id,
                    metadata={
                        "repository": repo,
                        "sha": c["sha"],
                        "files": [f["filename"] for f in files[:20]],
                    },
                )


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _describe_series(
    ns: str, name: str, dims: dict[str, str], period: int, pts: list[dict[str, Any]]
) -> str:
    values = [p["value"] for p in pts]
    n = len(values)
    k = max(1, n // 5)
    baseline = sum(values[:k]) / k
    recent = sum(values[-k:]) / k
    peak_i = max(range(n), key=lambda i: values[i])
    low_i = min(range(n), key=lambda i: values[i])
    change = None
    if baseline > 0:
        change = next(
            (
                pts[i]["timestamp"]
                for i in range(n)
                if values[i] >= 2 * baseline or values[i] <= 0.5 * baseline
            ),
            None,
        )
    pct = f" ({(recent - baseline) / baseline * 100:+.0f}%)" if baseline else ""
    step = max(1, n // 12)
    sample = ", ".join(f"{p['timestamp'][11:16]}={p['value']:g}" for p in pts[::step])
    lines = [
        f"{ns}/{name} {dims} at {period}s resolution, {n} datapoints from {pts[0]['timestamp']} to {pts[-1]['timestamp']}.",
        f"Baseline (mean of first {k} points): {baseline:.4g}. Recent (mean of last {k} points): {recent:.4g}{pct}.",
        f"Peak: {values[peak_i]:.4g} at {pts[peak_i]['timestamp']}. Minimum: {values[low_i]:.4g} at {pts[low_i]['timestamp']}.",
        f"First point at least 2x or at most 0.5x the baseline: {change}."
        if change
        else "No point moved to 2x or 0.5x of the baseline.",
        f"Sampled values (UTC time=value): {sample}",
    ]
    return "\n".join(lines)
