"""CloudWatch MCP server against LocalStack with the synthetic demo incident."""

import importlib.util
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

os.environ.setdefault("CW_ALLOWED_LOG_GROUPS", "/ecs/orders-api")
os.environ.setdefault("CW_ALLOWED_NAMESPACES", "OpsPilot/OrdersApi")

from mcp_servers.cloudwatch.server import _simple_terms, mcp  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def seeded() -> None:
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_cloudwatch.py"
    spec = importlib.util.spec_from_file_location("seed_cloudwatch", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


# The MCP client uses anyio cancel scopes, which must open and close in the same task,
# so each test opens its own in-process client instead of sharing an async fixture.
@asynccontextmanager
async def connect() -> AsyncIterator[Client]:
    async with Client(mcp) as c:
        yield c


def window(hours: float = 3) -> dict[str, str]:
    end = datetime.now(UTC) + timedelta(minutes=1)
    return {"start_time": (end - timedelta(hours=hours)).isoformat(), "end_time": end.isoformat()}


async def call(c: Client, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    r = await c.call_tool(tool, args)
    assert not r.is_error, r.content
    return dict(r.structured_content)


async def test_lists_only_allowlisted_groups() -> None:
    async with connect() as cw:
        assert (await call(cw, "list_log_groups", {}))["log_groups"] == ["/ecs/orders-api"]


async def test_filter_finds_deploy_and_config_change() -> None:
    async with connect() as cw:
        r = await call(
            cw,
            "filter_log_events",
            {"log_group": "/ecs/orders-api", "filter_pattern": '"maximum-pool-size"', **window()},
        )
        assert [e["message"] for e in r["events"]] == [
            "INFO  [config] spring.datasource.hikari.maximum-pool-size=10 (previous release: 50)"
        ]


async def test_filter_limit_and_truncation() -> None:
    async with connect() as cw:
        r = await call(
            cw,
            "filter_log_events",
            {
                "log_group": "/ecs/orders-api",
                "filter_pattern": "ERR_POOL_TIMEOUT",
                "limit": 5,
                **window(),
            },
        )
        assert r["returned"] == 5 and r["truncated"] is True
        assert all("ERR_POOL_TIMEOUT" in e["message"] for e in r["events"])


async def test_metric_shows_latency_step_change() -> None:
    async with connect() as cw:
        r = await call(
            cw,
            "get_metric_data",
            {
                "namespace": "OpsPilot/OrdersApi",
                "metric_name": "LatencyP95",
                "dimensions": {"Service": "orders-api"},
                "period_seconds": 300,
                **window(),
            },
        )
        values = [p["value"] for p in r["datapoints"]]
        assert min(values) < 300 and max(values) > 1500


async def test_alarm_and_history() -> None:
    async with connect() as cw:
        alarms = (await call(cw, "describe_alarms", {"state": "ALARM"}))["alarms"]
        assert [a["name"] for a in alarms] == ["orders-api-p95-latency"]
        hist = await call(
            cw, "get_alarm_history", {"alarm_name": "orders-api-p95-latency", **window()}
        )
        assert any("to ALARM" in h["summary"] for h in hist["history"])


@pytest.mark.parametrize(
    ("tool", "args", "message"),
    [
        ("filter_log_events", {"log_group": "/aws/secret"}, "not allowlisted"),
        ("get_metric_data", {"namespace": "AWS/RDS", "metric_name": "CPU"}, "not allowlisted"),
        (
            "filter_log_events",
            {
                "log_group": "/ecs/orders-api",
                "start_time": "2026-01-01T00:00:00Z",
                "end_time": "2026-01-03T00:00:00Z",
            },
            "24 hours",
        ),
        (
            "filter_log_events",
            {
                "log_group": "/ecs/orders-api",
                "start_time": "2026-01-01T00:00:00",
                "end_time": "2026-01-01T01:00:00",
            },
            "timezone",
        ),
    ],
)
async def test_rejections_are_explained(tool: str, args: dict[str, Any], message: str) -> None:
    async with connect() as cw:
        r = await cw.call_tool(tool, {**window(), **args})
        assert r.is_error and message in r.content[0].text  # type: ignore[union-attr]


def test_simple_term_parsing() -> None:
    assert _simple_terms('"maximum-pool-size" INFO') == ["maximum-pool-size", "INFO"]
    assert _simple_terms("ERROR -DEBUG") is None
    assert _simple_terms('{ $.level = "ERROR" }') is None
    assert _simple_terms("") is None


async def test_list_metrics_for_service() -> None:
    async with connect() as cw:
        r = await call(
            cw,
            "list_metrics",
            {"namespace": "OpsPilot/OrdersApi", "dimensions": {"Service": "orders-api"}},
        )
    names = {m["metric_name"] for m in r["metrics"]}
    assert {"LatencyP95", "Http5xxCount", "DbPoolActiveConnections"} <= names
