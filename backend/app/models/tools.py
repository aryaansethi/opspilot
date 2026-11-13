"""MCP servers, the server-side tool registry, tool invocations, and workspace integrations."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, TimestampMixin, WorkspaceScoped

INTEGRATION_KINDS = ("github", "cloudwatch", "jira")
TOOL_ACCESS = ("read", "write", "unknown")


class McpServer(IdMixin, TimestampMixin, Base):
    """A deployed MCP server process (global; workspaces opt in via integrations)."""

    __tablename__ = "mcp_servers"
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    url: Mapped[str] = mapped_column(String(512), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tools: Mapped[list["ToolRegistryEntry"]] = relationship(
        back_populates="server", lazy="selectin"
    )


class ToolRegistryEntry(IdMixin, TimestampMixin, Base):
    __tablename__ = "tool_registry"
    __table_args__ = (
        UniqueConstraint("server_id", "name", name="uq_tool_registry_server_name"),
        CheckConstraint(f"access IN {TOOL_ACCESS}", name="access_valid"),
    )
    server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mcp_servers.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    access: Mapped[str] = mapped_column(String(10), nullable=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=15000)
    max_result_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=64000)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    server: Mapped[McpServer] = relationship(back_populates="tools", lazy="joined")


class ConnectedIntegration(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    """A workspace's opt-in to an MCP server, with workspace-level allowlists in `config`."""

    __tablename__ = "connected_integrations"
    __table_args__ = (
        UniqueConstraint("workspace_id", "kind", name="uq_connected_integrations_ws_kind"),
        CheckConstraint(f"kind IN {INTEGRATION_KINDS}", name="kind_valid"),
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unchecked")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    # Per-workspace switches on top of the global registry (PATCH /integrations/{id}/tools/{tool}).
    disabled_tools: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )


class ToolInvocation(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "tool_invocations"
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tool_registry.id", ondelete="SET NULL")
    )
    server_name: Mapped[str] = mapped_column(String(80), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False)
    access: Mapped[str] = mapped_column(String(10), nullable=False)
    arguments_redacted: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    result_bytes: Mapped[int | None] = mapped_column(Integer)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text)
