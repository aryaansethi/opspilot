"""Read-only AWS CloudWatch MCP server.

Exposes a small, allowlisted, bounded set of CloudWatch Logs / Metrics / Alarms
reads. Locally it talks to LocalStack; in AWS it would use an IAM task role
with read-only permissions on the allowlisted resources only.

Run: uv run python -m mcp_servers.cloudwatch.server   (streamable HTTP on :8101/mcp)

Environment:
  CW_ALLOWED_LOG_GROUPS     comma-separated log group names (exact match)
  CW_ALLOWED_NAMESPACES     comma-separated metric namespaces
  AWS_ENDPOINT_URL, AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
"""

import asyncio
import os
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from mcp_servers.aws_compat import aws_client

MAX_WINDOW = timedelta(hours=24)
MAX_EVENTS = 500
MAX_MESSAGE_CHARS = 2000
MAX_DATAPOINTS = 1440
MAX_PAGES = 20
_TERM = re.compile(r'"([^"]+)"|(\S+)')

mcp = MCPServer(
    name="opspilot-cloudwatch",
    instructions="Read-only CloudWatch access limited to allowlisted log groups and namespaces.",
)


class ToolInputError(ToolError):
    """Rejected input; the message is returned to the caller."""


def _allow(var: str) -> set[str]:
    return {x.strip() for x in os.environ.get(var, "").split(",") if x.strip()}


@lru_cache
def _client(service: str) -> Any:
    return aws_client(
        service, endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    )


def _window(start_time: str, end_time: str) -> tuple[datetime, datetime]:
    try:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    except ValueError:
        raise ToolInputError("start_time/end_time must be ISO-8601 timestamps") from None
    if start.tzinfo is None or end.tzinfo is None:
        raise ToolInputError("Timestamps must include a timezone (e.g. 2026-11-13T09:00:00Z)")
    if end <= start:
        raise ToolInputError("end_time must be after start_time")
    if end - start > MAX_WINDOW:
        raise ToolInputError("Time window may not exceed 24 hours")
    return start, end


def _check_log_group(name: str) -> None:
    if name not in _allow("CW_ALLOWED_LOG_GROUPS"):
        raise ToolInputError(f"Log group '{name}' is not allowlisted for this integration")


def _check_namespace(ns: str) -> None:
    if ns not in _allow("CW_ALLOWED_NAMESPACES"):
        raise ToolInputError(f"Metric namespace '{ns}' is not allowlisted for this integration")


def _simple_terms(pattern: str) -> list[str] | None:
    """Terms of a plain CloudWatch term pattern (all must match), or None if complex/empty."""
    if not pattern.strip() or any(ch in pattern for ch in "{}[]?="):
        return None
    terms = _TERM.findall(pattern)
    if any(bare.startswith(("-", "+")) for _, bare in terms):  # exclusions / optional terms
        return None
    return [quoted or bare for quoted, bare in terms]


def _iso(ms_or_dt: int | datetime) -> str:
    dt = (
        ms_or_dt if isinstance(ms_or_dt, datetime) else datetime.fromtimestamp(ms_or_dt / 1000, UTC)
    )
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


@mcp.tool(description="List allowlisted CloudWatch log groups.")
async def list_log_groups() -> dict[str, Any]:
    allowed = _allow("CW_ALLOWED_LOG_GROUPS")
    resp = await asyncio.to_thread(_client("logs").describe_log_groups, limit=50)
    groups = [g["logGroupName"] for g in resp.get("logGroups", []) if g["logGroupName"] in allowed]
    return {"log_groups": sorted(groups)}


@mcp.tool(
    description="Search log events in one allowlisted log group within a time window "
    '(max 24h). Optional CloudWatch filter pattern, e.g. ERROR or "HikariPool".'
)
async def filter_log_events(
    log_group: Annotated[str, Field(max_length=512)],
    start_time: Annotated[str, Field(description="ISO-8601 with timezone")],
    end_time: Annotated[str, Field(description="ISO-8601 with timezone")],
    filter_pattern: Annotated[str, Field(max_length=256)] = "",
    limit: Annotated[int, Field(ge=1, le=MAX_EVENTS)] = 100,
) -> dict[str, Any]:
    _check_log_group(log_group)
    start, end = _window(start_time, end_time)
    terms = _simple_terms(filter_pattern)
    kwargs: dict[str, Any] = {
        "logGroupName": log_group,
        "startTime": int(start.timestamp() * 1000),
        "endTime": int(end.timestamp() * 1000),
        "limit": 1000,
    }
    if filter_pattern:
        kwargs["filterPattern"] = filter_pattern
    events: list[dict[str, Any]] = []
    truncated = False
    for _ in range(MAX_PAGES):
        resp = await asyncio.to_thread(_client("logs").filter_log_events, **kwargs)
        for e in resp.get("events", []):
            msg = e["message"]
            # Re-apply simple term patterns server-side (LocalStack only partially implements
            # filter patterns; on real AWS this is a no-op because results already match).
            if terms is not None and not all(t in msg for t in terms):
                continue
            if len(events) >= limit:
                truncated = True
                break
            events.append(
                {
                    "timestamp": _iso(e["timestamp"]),
                    "log_stream": e.get("logStreamName"),
                    "message": msg[:MAX_MESSAGE_CHARS],
                }
            )
        token = resp.get("nextToken")
        if truncated or not token:
            break
        kwargs["nextToken"] = token
    else:
        truncated = True
    events.sort(key=lambda e: e["timestamp"])
    return {
        "log_group": log_group,
        "window": {"start": _iso(start), "end": _iso(end)},
        "filter_pattern": filter_pattern,
        "events": events,
        "returned": len(events),
        "truncated": truncated,
    }


@mcp.tool(description="Get a CloudWatch metric time series for an allowlisted namespace.")
async def get_metric_data(
    namespace: Annotated[str, Field(max_length=256)],
    metric_name: Annotated[str, Field(max_length=256)],
    start_time: str,
    end_time: str,
    dimensions: dict[str, str] | None = None,
    period_seconds: Annotated[int, Field(ge=60, le=3600)] = 60,
    stat: Literal[
        "Average", "Sum", "Maximum", "Minimum", "SampleCount", "p50", "p95", "p99"
    ] = "Average",
) -> dict[str, Any]:
    _check_namespace(namespace)
    start, end = _window(start_time, end_time)
    if (end - start).total_seconds() / period_seconds > MAX_DATAPOINTS:
        raise ToolInputError("Too many datapoints; increase period_seconds")
    dims = [{"Name": k, "Value": v} for k, v in (dimensions or {}).items()]
    resp = await asyncio.to_thread(
        _client("cloudwatch").get_metric_data,
        MetricDataQueries=[
            {
                "Id": "m1",
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": metric_name,
                        "Dimensions": dims,
                    },
                    "Period": period_seconds,
                    "Stat": stat,
                },
            }
        ],
        StartTime=start,
        EndTime=end,
    )
    result = (resp.get("MetricDataResults") or [{}])[0]
    pairs: list[tuple[str, float]] = sorted(
        (_iso(t), round(float(v), 4))
        for t, v in zip(result.get("Timestamps", []), result.get("Values", []), strict=False)
    )
    points = [{"timestamp": ts, "value": v} for ts, v in pairs]
    values = [v for _, v in pairs]
    return {
        "namespace": namespace,
        "metric_name": metric_name,
        "dimensions": dimensions or {},
        "stat": stat,
        "period_seconds": period_seconds,
        "window": {"start": _iso(start), "end": _iso(end)},
        "datapoints": points,
        "summary": {
            "count": len(values),
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "mean": round(sum(values) / len(values), 4) if values else None,
        },
    }


@mcp.tool(description="Describe CloudWatch alarms, optionally by name prefix and state.")
async def describe_alarms(
    alarm_name_prefix: Annotated[str, Field(max_length=255)] = "",
    state: Literal["OK", "ALARM", "INSUFFICIENT_DATA"] | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"MaxRecords": 50}
    if alarm_name_prefix:
        kwargs["AlarmNamePrefix"] = alarm_name_prefix
    if state:
        kwargs["StateValue"] = state
    resp = await asyncio.to_thread(_client("cloudwatch").describe_alarms, **kwargs)
    allowed_ns = _allow("CW_ALLOWED_NAMESPACES")
    alarms = [
        {
            "name": a["AlarmName"],
            "state": a["StateValue"],
            "reason": a.get("StateReason"),
            "updated_at": _iso(a["StateUpdatedTimestamp"])
            if a.get("StateUpdatedTimestamp")
            else None,
            "metric": a.get("MetricName"),
            "namespace": a.get("Namespace"),
            "threshold": a.get("Threshold"),
            "comparison": a.get("ComparisonOperator"),
        }
        for a in resp.get("MetricAlarms", [])
        if a.get("Namespace") in allowed_ns
    ]
    return {"alarms": alarms}


@mcp.tool(description="State-change history for one alarm within a time window (max 24h).")
async def get_alarm_history(
    alarm_name: Annotated[str, Field(max_length=255)], start_time: str, end_time: str
) -> dict[str, Any]:
    start, end = _window(start_time, end_time)
    names = {a["name"] for a in (await describe_alarms(alarm_name_prefix=alarm_name))["alarms"]}
    if alarm_name not in names:
        raise ToolInputError(f"Alarm '{alarm_name}' not found in allowlisted namespaces")
    resp = await asyncio.to_thread(
        _client("cloudwatch").describe_alarm_history,
        AlarmName=alarm_name,
        HistoryItemType="StateUpdate",
        StartDate=start,
        EndDate=end,
        MaxRecords=100,
    )
    items = [
        {"timestamp": _iso(h["Timestamp"]), "summary": h.get("HistorySummary")}
        for h in resp.get("AlarmHistoryItems", [])
    ]
    return {"alarm_name": alarm_name, "history": sorted(items, key=lambda i: i["timestamp"])}


def main() -> None:
    host = os.environ.get("MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("MCP_PORT", "8101"))
    asyncio.run(mcp.run_streamable_http_async(host=host, port=port))


if __name__ == "__main__":
    main()
