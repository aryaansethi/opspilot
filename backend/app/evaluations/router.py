"""Evaluation dashboard API. Runs are queued to the worker; results are real measurements only."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.auth.deps import DB, Workspace
from app.core.config import get_settings
from app.core.errors import AppError, Forbidden, NotFound
from app.documents import storage
from app.evaluations.runner import DATASET_NAME, RETRIEVAL_CONFIGS, load_dataset
from app.models import EvaluationResult, EvaluationRun

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
ANSWERS_LABEL = "answers_hybrid_rrf"


class RunRequest(BaseModel):
    dataset_version: str | None = None
    config_label: str | None = (
        None  # one of RETRIEVAL_CONFIGS, "answers_hybrid_rrf", or None for all retrieval configs
    )
    split: Literal["test", "tune", "all"] = "test"
    limit: int | None = Field(default=None, ge=1, le=500)  # answers runs only


class RunOut(BaseModel):
    id: uuid.UUID
    dataset_name: str
    dataset_version: str
    dataset_hash: str
    kind: str
    config_label: str
    config: dict[str, Any]
    split: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    metrics: dict[str, Any] | None
    error: str | None


class ResultOut(BaseModel):
    question_id: str
    question: str
    kind: str
    answerable: bool
    hit_at_5: bool
    reciprocal_rank: float
    latency_ms: float
    detail: dict[str, Any]


class RunDetailOut(RunOut):
    results: list[ResultOut]


def _out(r: EvaluationRun) -> RunOut:
    return RunOut(
        id=r.id,
        dataset_name=r.dataset_name,
        dataset_version=r.dataset_version,
        dataset_hash=r.dataset_hash,
        kind=r.kind,
        config_label=r.config_label,
        config=r.config,
        split=r.split,
        status=r.status,
        started_at=r.started_at,
        finished_at=r.finished_at,
        metrics=r.metrics,
        error=r.error,
    )


@router.post("/run", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: RunRequest, db: DB, ctx: Workspace) -> RunOut:
    """Queue one configuration, or all four retrieval configurations when none is given (returns the first)."""
    if ctx.role != "owner":
        raise Forbidden("Only workspace owners can start evaluation runs")
    ds = load_dataset()
    if body.dataset_version and body.dataset_version != ds.version:
        raise AppError(f"Only dataset {ds.version} is available")
    labels = [body.config_label] if body.config_label else list(RETRIEVAL_CONFIGS)
    for label in labels:
        if label not in RETRIEVAL_CONFIGS and label != ANSWERS_LABEL:
            raise AppError(
                f"Unknown config '{label}'. Use one of {[*RETRIEVAL_CONFIGS, ANSWERS_LABEL]}"
            )
    runs = []
    for label in labels:
        run = EvaluationRun(
            dataset_name=DATASET_NAME,
            dataset_version=ds.version,
            dataset_hash=ds.hash,
            kind="answers" if label == ANSWERS_LABEL else "retrieval",
            config_label=label,
            config={},
            split=body.split,
            status="running",
            started_at=datetime.now(UTC),
            requested_by=ctx.user.id,
        )
        db.add(run)
        runs.append(run)
    await db.commit()
    for run in runs:
        await storage.enqueue(
            get_settings().sqs_evaluate_queue,
            {
                "run_id": str(run.id),
                "config_label": run.config_label,
                "split": run.split,
                "limit": body.limit,
            },
        )
    return _out(runs[0])


@router.get("/runs", response_model=list[RunOut])
async def list_runs(db: DB, ctx: Workspace, limit: int = Query(50, ge=1, le=200)) -> list[RunOut]:
    rows = await db.scalars(
        select(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(limit)
    )
    return [_out(r) for r in rows]


@router.get("/runs/{run_id}", response_model=RunDetailOut)
async def get_run(run_id: uuid.UUID, db: DB, ctx: Workspace) -> RunDetailOut:
    run = await db.get(EvaluationRun, run_id)
    if run is None:
        raise NotFound("Evaluation run not found")
    rows = await db.scalars(
        select(EvaluationResult)
        .where(EvaluationResult.run_id == run.id)
        .order_by(EvaluationResult.question_id)
    )
    return RunDetailOut(
        **_out(run).model_dump(),
        results=[
            ResultOut(
                question_id=r.question_id,
                question=r.question,
                kind=r.kind,
                answerable=r.answerable,
                hit_at_5=r.hit_at_5,
                reciprocal_rank=r.reciprocal_rank,
                latency_ms=round(r.latency_ms, 1),
                detail=r.detail,
            )
            for r in rows
        ],
    )
