"""Rule-based request classification and parameter validation (no LLM needed)."""

import re
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.errors import AppError

INCIDENT_TYPES = (
    "api_latency",
    "error_rate",
    "db_connection",
    "deployment_failure",
    "memory_pressure",
    "config_issue",
    "other",
)
_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "db_connection",
        re.compile(
            r"\b(connection pool|hikari|db connection|database connection|too many connections|pool exhaust)",
            re.I,
        ),
    ),
    ("api_latency", re.compile(r"\b(latency|slow|timeouts?|timed out|p9[59]|response time)", re.I)),
    ("error_rate", re.compile(r"\b(5\d\d|errors?|exceptions?|failures?|failing)\b", re.I)),
    ("memory_pressure", re.compile(r"\b(memory|oom|out of memory|heap|gc pause)", re.I)),
    (
        "deployment_failure",
        re.compile(r"\b(deploy(ment)? fail|rollout|rollback|crash ?loop)", re.I),
    ),
    (
        "config_issue",
        re.compile(r"\b(config(uration)?|env var|feature flag|missing setting)", re.I),
    ),
]


def classify(question: str) -> str:
    for kind, pattern in _RULES:
        if pattern.search(question):
            return kind
    return "other"


def missing_parameters(
    service: str | None, time_start: datetime | None, time_end: datetime | None
) -> list[str]:
    missing = []
    if not service:
        missing.append("service")
    if time_start is None or time_end is None:
        missing.append("time_range")
    return missing


def validate_window(time_start: datetime | None, time_end: datetime | None) -> None:
    if (time_start is None) != (time_end is None):
        raise AppError("Provide both time_start and time_end, or neither")
    if time_start is None or time_end is None:
        return
    if time_start.tzinfo is None or time_end.tzinfo is None:
        raise AppError("time_start and time_end must include a timezone")
    if time_end <= time_start:
        raise AppError("time_end must be after time_start")
    hours = get_settings().investigation_max_window_hours
    if time_end - time_start > timedelta(hours=hours):
        raise AppError(f"The time window may not exceed {hours} hours")
    if time_start > datetime.now(UTC) + timedelta(minutes=5):
        raise AppError("time_start is in the future")
