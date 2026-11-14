"""Investigations, their event log, evidence, hypotheses, reports, and action approvals."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, WorkspaceScoped

STATES = (
    "RECEIVED",
    "CLASSIFY_REQUEST",
    "COLLECT_PARAMETERS",
    "AWAITING_PARAMETERS",
    "PLAN_INVESTIGATION",
    "RUN_KNOWLEDGE_RETRIEVAL",
    "RUN_READ_TOOLS",
    "NORMALIZE_EVIDENCE",
    "ANALYZE_HYPOTHESES",
    "CHECK_CITATIONS",
    "GENERATE_REPORT",
    "AWAITING_ACTION",
    "COMPLETED",
    "PARTIAL",
    "FAILED_INVALID_PARAMS",
    "FAILED_LLM",
    "FAILED_RETRIEVAL",
)
TERMINAL_STATES = (
    "COMPLETED",
    "PARTIAL",
    "FAILED_INVALID_PARAMS",
    "FAILED_LLM",
    "FAILED_RETRIEVAL",
)
WAITING_STATES = ("AWAITING_PARAMETERS", "AWAITING_ACTION")
SOURCE_SYSTEMS = ("knowledge_base", "github", "cloudwatch", "jira")
HYPOTHESIS_STATUSES = ("proposed", "supported", "refuted", "confirmed")
APPROVAL_STATUSES = ("pending", "approved", "rejected", "executed", "failed")


class Investigation(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "investigations"
    __table_args__ = (CheckConstraint(f"state IN {STATES}", name="state_valid"),)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    service: Mapped[str | None] = mapped_column(String(120))
    environment: Mapped[str | None] = mapped_column(String(40))
    time_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    incident_type: Mapped[str | None] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="RECEIVED", index=True)
    missing_parameters: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    failed_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    # Per-stage wall-clock milliseconds of the last run (plan_llm, knowledge_retrieval, read_tools,
    # analysis_llm, report, total). Stages that did not run are absent.
    timings_ms: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InvestigationEvent(IdMixin, WorkspaceScoped, Base):
    """Append-only progress log; feeds the SSE stream and its Last-Event-ID replay."""

    __tablename__ = "investigation_events"
    __table_args__ = (
        UniqueConstraint("investigation_id", "seq", name="uq_investigation_events_seq"),
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceItem(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        UniqueConstraint("investigation_id", "label", name="uq_evidence_items_label"),
        CheckConstraint(f"source_system IN {SOURCE_SYSTEMS}", name="source_system_valid"),
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(8), nullable=False)  # E1, E2, ... used in prompts
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(600), nullable=False)
    url: Mapped[str | None] = mapped_column(String(600))
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_range: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    retrieval_method: Mapped[str | None] = mapped_column(String(80))
    rank: Mapped[int | None] = mapped_column(Integer)
    reliability_notes: Mapped[str | None] = mapped_column(Text)
    tool_invocation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    item_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )


class Hypothesis(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "hypotheses"
    __table_args__ = (CheckConstraint(f"status IN {HYPOTHESIS_STATUSES}", name="status_valid"),)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="proposed")
    supporting_evidence_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    contradicting_evidence_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    missing_evidence: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence_explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validation_steps: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)


class InvestigationReport(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "investigation_reports"
    __table_args__ = (
        UniqueConstraint("investigation_id", "version", name="uq_investigation_reports_v"),
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)


class ActionApproval(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    """A proposed write action. Nothing executes until a member approves this exact row."""

    __tablename__ = "action_approvals"
    __table_args__ = (CheckConstraint(f"status IN {APPROVAL_STATUSES}", name="status_valid"),)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    server: Mapped[str] = mapped_column(String(80), nullable=False)
    tool: Mapped[str] = mapped_column(String(120), nullable=False)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", index=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
