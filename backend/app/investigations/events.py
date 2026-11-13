"""Investigation progress events.

Writers append a row to `investigation_events` and `pg_notify` in the same
transaction (Postgres delivers the notification only on commit). Readers (the
SSE endpoint) replay rows after Last-Event-ID, then LISTEN for new ones. No Redis.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import asyncpg
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Investigation, InvestigationEvent

CHANNEL = "investigation_events"
EVENT_TYPES = (
    "state_changed",
    "step_started",
    "step_completed",
    "step_failed",
    "tool_call_started",
    "tool_call_completed",
    "evidence_added",
    "hypothesis_added",
    "report_ready",
    "approval_requested",
    "parameters_required",
    "error",
)


async def emit(
    db: AsyncSession, inv: Investigation, type_: str, payload: dict[str, Any] | None = None
) -> InvestigationEvent:
    """Append an event and commit (so listeners see it immediately)."""
    assert type_ in EVENT_TYPES, type_
    # Serialise seq allocation per investigation.
    await db.execute(select(Investigation.id).where(Investigation.id == inv.id).with_for_update())
    seq = (
        await db.scalar(
            select(func.coalesce(func.max(InvestigationEvent.seq), 0)).where(
                InvestigationEvent.investigation_id == inv.id
            )
        )
        or 0
    ) + 1
    ev = InvestigationEvent(
        workspace_id=inv.workspace_id,
        investigation_id=inv.id,
        seq=seq,
        type=type_,
        payload=payload or {},
        at=datetime.now(UTC),
    )
    db.add(ev)
    await db.flush()
    await db.execute(text("SELECT pg_notify(:c, :p)"), {"c": CHANNEL, "p": f"{inv.id}:{seq}"})
    await db.commit()
    return ev


def to_dict(ev: InvestigationEvent) -> dict[str, Any]:
    return {"seq": ev.seq, "type": ev.type, "payload": ev.payload, "at": ev.at.isoformat()}


def sse_frame(ev: InvestigationEvent) -> str:
    return f"id: {ev.seq}\nevent: {ev.type}\ndata: {json.dumps(to_dict(ev), default=str)}\n\n"


async def events_after(
    db: AsyncSession, investigation_id: uuid.UUID, after_seq: int
) -> list[InvestigationEvent]:
    rows = await db.scalars(
        select(InvestigationEvent)
        .where(
            InvestigationEvent.investigation_id == investigation_id,
            InvestigationEvent.seq > after_seq,
        )
        .order_by(InvestigationEvent.seq)
    )
    return list(rows)


def _raw_dsn() -> str:
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def stream(
    db: AsyncSession,
    investigation_id: uuid.UUID,
    after_seq: int,
    *,
    follow: bool = True,
    keepalive_seconds: float = 15.0,
    max_seconds: float = 600.0,
) -> AsyncIterator[str]:
    """Yield SSE frames: replay, then live. With follow=False, replay only and stop."""
    last = after_seq
    for ev in await events_after(db, investigation_id, last):
        last = ev.seq
        yield sse_frame(ev)
    if not follow:
        return

    wake = asyncio.Event()

    def on_notify(_conn: Any, _pid: int, _channel: str, payload: str) -> None:
        if payload.startswith(f"{investigation_id}:"):
            wake.set()

    conn = await asyncpg.connect(_raw_dsn())
    try:
        await conn.add_listener(CHANNEL, on_notify)
        # Close the gap between the replay query and LISTEN starting.
        wake.set()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max_seconds
        while loop.time() < deadline:
            try:
                await asyncio.wait_for(wake.wait(), timeout=keepalive_seconds)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            wake.clear()
            await db.rollback()  # end any open snapshot so new rows are visible
            for ev in await events_after(db, investigation_id, last):
                last = ev.seq
                yield sse_frame(ev)
    finally:
        await conn.remove_listener(CHANNEL, on_notify)
        await conn.close()
