"""Job safety: atomic claims (no duplicate execution) and a reaper (nothing stays running forever).

SQS can deliver a message twice, and two workers may run at once. A job is executed only by
the worker whose conditional UPDATE succeeds. A job whose worker died is reclaimed after it
has made no progress for longer than its timeout, or marked failed by the reaper.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.models import EvaluationRun, Investigation
from app.models.investigations import TERMINAL_STATES, WAITING_STATES

EVALUATION_STALE_AFTER = timedelta(
    hours=4
)  # longest legitimate run: answers + judge on v2 (~1.5 h)
LOST_MESSAGE_AFTER = timedelta(minutes=15)


class AlreadyClaimed(Exception):
    """Another worker is running (or already ran) this job: acknowledge the message, do nothing."""


def investigation_stale_after() -> timedelta:
    return timedelta(seconds=get_settings().investigation_timeout_seconds + 120)


async def claim_investigation(db: AsyncSession, investigation_id: uuid.UUID) -> bool:
    """True if this worker may run the investigation now."""
    now = datetime.now(UTC)
    done = (*TERMINAL_STATES, *WAITING_STATES)
    result = await db.execute(
        update(Investigation)
        .where(
            Investigation.id == investigation_id,
            (Investigation.state == "RECEIVED")
            | (
                Investigation.state.not_in(done)
                & (Investigation.updated_at < now - investigation_stale_after())
            ),
        )
        .values(state="CLASSIFY_REQUEST", started_at=now, updated_at=now)
        .returning(Investigation.id)
        .execution_options(synchronize_session=False)
    )
    claimed = result.scalar_one_or_none() is not None
    await db.commit()
    return claimed


async def claim_evaluation(db: AsyncSession, run_id: uuid.UUID) -> bool:
    now = datetime.now(UTC)
    result = await db.execute(
        update(EvaluationRun)
        .where(
            EvaluationRun.id == run_id,
            EvaluationRun.status == "running",
            EvaluationRun.claimed_at.is_(None)
            | (EvaluationRun.claimed_at < now - EVALUATION_STALE_AFTER),
        )
        .values(claimed_at=now)
        .returning(EvaluationRun.id)
        .execution_options(synchronize_session=False)
    )
    claimed = result.scalar_one_or_none() is not None
    await db.commit()
    return claimed


async def reap(db: AsyncSession) -> dict[str, int]:
    """Mark stuck jobs; re-queue investigations whose queue message was lost."""
    from app.documents import storage
    from app.investigations.events import emit

    now = datetime.now(UTC)
    counts = {"investigations_failed": 0, "investigations_requeued": 0, "evaluations_failed": 0}
    done = (*TERMINAL_STATES, *WAITING_STATES, "RECEIVED")
    stuck = list(
        await db.scalars(
            select(Investigation).where(
                Investigation.state.not_in(done),
                Investigation.updated_at < now - investigation_stale_after(),
            )
        )
    )
    for inv in stuck:
        minutes = int((now - inv.updated_at).total_seconds() // 60)
        previous = inv.state
        inv.state, inv.finished_at = "PARTIAL", now
        inv.error = (
            "The worker stopped before this investigation finished "
            f"(no progress for {minutes} minutes)."
        )
        inv.failed_steps = [*(inv.failed_steps or []), f"{previous}: worker stopped"]
        await db.flush()
        await emit(db, inv, "error", {"message": inv.error})
        await emit(db, inv, "state_changed", {"from": previous, "to": "PARTIAL"})
        counts["investigations_failed"] += 1
    lost = list(
        await db.scalars(
            select(Investigation).where(
                Investigation.state == "RECEIVED",
                Investigation.updated_at < now - LOST_MESSAGE_AFTER,
            )
        )
    )
    for inv in lost:
        inv.updated_at = now  # wait another interval before re-queueing again
        await db.commit()
        await storage.enqueue(
            get_settings().sqs_investigate_queue,
            {"investigation_id": str(inv.id), "workspace_id": str(inv.workspace_id)},
        )
        counts["investigations_requeued"] += 1
    runs = list(
        await db.scalars(
            select(EvaluationRun).where(
                EvaluationRun.status == "running",
                (
                    (EvaluationRun.claimed_at.is_not(None))
                    & (EvaluationRun.claimed_at < now - EVALUATION_STALE_AFTER)
                )
                | (
                    EvaluationRun.claimed_at.is_(None)
                    & (EvaluationRun.started_at < now - EVALUATION_STALE_AFTER)
                ),
            )
        )
    )
    for run in runs:
        run.status, run.finished_at = "failed", now
        run.error = (
            "No progress for over 4 hours; the worker probably stopped. Start the run again."
        )
        counts["evaluations_failed"] += 1
    await db.commit()
    if any(counts.values()):
        log.warning("jobs.reaped", **counts)
    return counts
