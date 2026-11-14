"""Evaluation runs and per-question results (global: the evaluation corpus is synthetic)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class EvaluationRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    dataset_name: Mapped[str] = mapped_column(String(80), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    dataset_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # retrieval | answers
    config_label: Mapped[str] = mapped_column(String(80), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    split: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class EvaluationResult(IdMixin, TimestampMixin, Base):
    __tablename__ = "evaluation_results"
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(String(20), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hit_at_5: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reciprocal_rank: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
