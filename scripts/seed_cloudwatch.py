"""Seed LocalStack CloudWatch with a SYNTHETIC demo incident (clearly fake data).

Scenario (relative to now): orders-api release 4.3 deployed 60 minutes ago; it
lowered the DB pool size, latency and 5xx rose, an alarm fired. Used only for
local demos and tests — never presented as real production data.

Note: CloudWatch has no "delete metric data" API, so re-running adds more samples to
the same metrics. Averages stay realistic; Sum statistics grow with each run.

Usage: uv run --project backend python scripts/seed_cloudwatch.py
"""

import os
import random
from datetime import UTC, datetime, timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from mcp_servers.aws_compat import aws_client  # noqa: E402

LOG_GROUP = "/ecs/orders-api"
NAMESPACE = "OpsPilot/OrdersApi"
DIMS = [{"Name": "Service", "Value": "orders-api"}]
ALARM = "orders-api-p95-latency"


def client(name: str):  # type: ignore[no-untyped-def]
    return aws_client(
        name, endpoint_url=os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
    )


def main() -> None:
    rnd = random.Random(42)
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    start = now - timedelta(minutes=120)
    deploy = now - timedelta(minutes=60)
    logs, cw = client("logs"), client("cloudwatch")

    try:
        logs.delete_log_group(logGroupName=LOG_GROUP)
    except logs.exceptions.ResourceNotFoundException:
        pass
    logs.create_log_group(logGroupName=LOG_GROUP)
    logs.create_log_stream(logGroupName=LOG_GROUP, logStreamName="orders-api/task-1")

    events = []
    t = start
    while t < now:
        ms = int(t.timestamp() * 1000)
        if t < deploy:
            events.append((ms, f"INFO  [http] POST /orders 201 {rnd.randint(120, 220)}ms"))
        else:
            if rnd.random() < 0.55:
                events.append(
                    (
                        ms,
                        "ERROR [db] HikariPool-1 - Connection is not available, request timed out after 30000ms code=ERR_POOL_TIMEOUT",
                    )
                )
                events.append(
                    (ms + 5, f"ERROR [http] POST /orders 500 {rnd.randint(28000, 30500)}ms")
                )
            else:
                events.append((ms, f"INFO  [http] POST /orders 201 {rnd.randint(900, 2600)}ms"))
        if t == deploy:
            events.append(
                (
                    ms - 1,
                    "INFO  [deploy] Started orders-api release 4.3 (task definition orders-api:87)",
                )
            )
            events.append(
                (
                    ms,
                    "INFO  [config] spring.datasource.hikari.maximum-pool-size=10 (previous release: 50)",
                )
            )
        t += timedelta(seconds=30)
    events.sort()
    for i in range(0, len(events), 500):
        logs.put_log_events(
            logGroupName=LOG_GROUP,
            logStreamName="orders-api/task-1",
            logEvents=[{"timestamp": ts, "message": m} for ts, m in events[i : i + 500]],
        )

    data = []
    t = start
    while t < now:
        after = t >= deploy
        latency = rnd.uniform(1800, 2600) if after else rnd.uniform(150, 210)
        errors = rnd.randint(25, 60) if after else rnd.randint(0, 2)
        active = 10 if after else rnd.randint(12, 22)
        for name, value, unit in (
            ("LatencyP95", latency, "Milliseconds"),
            ("Http5xxCount", errors, "Count"),
            ("DbPoolActiveConnections", active, "Count"),
        ):
            data.append(
                {
                    "MetricName": name,
                    "Dimensions": DIMS,
                    "Timestamp": t,
                    "Value": value,
                    "Unit": unit,
                }
            )
        t += timedelta(minutes=1)
    for i in range(0, len(data), 500):
        cw.put_metric_data(Namespace=NAMESPACE, MetricData=data[i : i + 500])

    cw.put_metric_alarm(
        AlarmName=ALARM,
        Namespace=NAMESPACE,
        MetricName="LatencyP95",
        Dimensions=DIMS,
        Statistic="Average",
        Period=60,
        EvaluationPeriods=3,
        Threshold=1000.0,
        ComparisonOperator="GreaterThanThreshold",
        ActionsEnabled=False,
    )
    cw.set_alarm_state(AlarmName=ALARM, StateValue="OK", StateReason="Latency within threshold")
    cw.set_alarm_state(
        AlarmName=ALARM,
        StateValue="ALARM",
        StateReason="Threshold Crossed: 3 datapoints were greater than the threshold (1000.0).",
    )
    print(f"seeded {len(events)} log events, {len(data)} metric points, alarm {ALARM}")
    print(f"window: {start.isoformat()} .. {now.isoformat()}  deploy at {deploy.isoformat()}")


if __name__ == "__main__":
    main()
