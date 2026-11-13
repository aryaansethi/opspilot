"""Static, reviewed policy for every MCP tool OpsPilot knows about.

A tool reported by an MCP server is only enabled if it appears here. Anything
else is registered as `unknown` and disabled, so a server cannot silently add
capabilities (including write actions) to the agent.
"""

from dataclasses import dataclass
from typing import Any

from app.core.errors import AppError


@dataclass(frozen=True)
class ToolPolicy:
    access: str  # "read" | "write"
    timeout_ms: int = 15000
    max_result_bytes: int = 64000
    requires_approval: bool = False


CATALOG: dict[str, dict[str, ToolPolicy]] = {
    "cloudwatch": {
        "list_log_groups": ToolPolicy("read", 10000, 16000),
        "list_metrics": ToolPolicy("read", 10000, 32000),
        "filter_log_events": ToolPolicy("read", 20000, 96000),
        "get_metric_data": ToolPolicy("read", 15000, 64000),
        "describe_alarms": ToolPolicy("read", 10000, 32000),
        "get_alarm_history": ToolPolicy("read", 10000, 32000),
    },
    "github": {
        "list_recent_commits": ToolPolicy("read", 15000, 64000),
        "get_commit_details": ToolPolicy("read", 15000, 96000),
        "list_pull_requests": ToolPolicy("read", 15000, 64000),
        "get_pull_request": ToolPolicy("read", 15000, 96000),
        "search_code": ToolPolicy("read", 20000, 64000),
    },
}


# ---- workspace-level argument policy (defence in depth on top of server allowlists) ----

INTEGRATION_CONFIG_SCHEMAS: dict[str, dict[str, Any]] = {
    "cloudwatch": {
        "type": "object",
        "properties": {
            "log_groups": {
                "type": "array",
                "items": {"type": "string", "maxLength": 512},
                "maxItems": 50,
            },
            "namespaces": {
                "type": "array",
                "items": {"type": "string", "maxLength": 256},
                "maxItems": 50,
            },
            "region": {"type": "string", "maxLength": 32},
        },
        "required": ["log_groups", "namespaces"],
        "additionalProperties": False,
    },
    "github": {
        "type": "object",
        "properties": {
            "repositories": {
                "type": "array",
                "items": {"type": "string", "pattern": "^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"},
                "minItems": 1,
                "maxItems": 20,
            },
        },
        "required": ["repositories"],
        "additionalProperties": False,
    },
}


def check_arguments_against_workspace(
    kind: str, tool: str, args: dict[str, Any], config: dict[str, Any]
) -> None:
    if kind == "cloudwatch":
        if "log_group" in args and args["log_group"] not in config.get("log_groups", []):
            raise AppError(f"Log group '{args['log_group']}' is not enabled for this workspace")
        if "namespace" in args and args["namespace"] not in config.get("namespaces", []):
            raise AppError(f"Namespace '{args['namespace']}' is not enabled for this workspace")
    elif kind == "github":
        repo = args.get("repository")
        if repo is not None and repo not in config.get("repositories", []):
            raise AppError(f"Repository '{repo}' is not enabled for this workspace")
