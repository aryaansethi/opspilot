"""No duplicate execution, and nothing stays running forever."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from app.db.session import get_sessionmaker
from app.evaluations.runner import RETRIEVAL_CONFIGS, load_dataset, run_retrieval
from app.jobs import AlreadyClaimed, claim_evaluation, claim_investigation, reap
from app.models import EvaluationRun, Investigation
from app.rag.embeddings.provider import HashingEmbeddings
from tests.conftest import register
from tests.test_documents import ws_headers
from tests.test_investigations import ScriptedLLM, run, start, window

API = "/api/v1"


async def _age(inv_id: str, state: str, minutes: int) -> None:
    async with get_sessionmaker()() as db:
        await db.execute(
            update(Investigation)
            .where(Investigation.id == uuid.UUID(inv_id))
            .values(state=state, updated_at=datetime.now(UTC) - timedelta(minutes=minutes))
        )
        await db.commit()


async def test_investigation_runs_once_even_if_delivered_twice(client: AsyncClient) -> None:
    u = await register(client)
    inv_id = await start(client, ws_headers(u), service="orders-api", **window())
    async with get_sessionmaker()() as db:
        assert await claim_investigation(db, uuid.UUID(inv_id)) is True
        assert (
            await claim_investigation(db, uuid.UUID(inv_id)) is False
        )  # second delivery while running
    llm = ScriptedLLM()
    assert (
        await run(inv_id, llm) == "CLASSIFY_REQUEST" and llm.calls == []
    )  # skipped, nothing executed


async def test_stalled_investigation_can_be_reclaimed(client: AsyncClient) -> None:
    u = await register(client)
    inv_id = await start(client, ws_headers(u), service="orders-api", **window())
    await _age(inv_id, "RUN_READ_TOOLS", minutes=60)  # its worker died an hour ago
    assert await run(inv_id, ScriptedLLM()) == "COMPLETED"
    import json

    text = (
        await client.get(
            f"{API}/investigations/{inv_id}/events?follow=false", headers=ws_headers(u)
        )
    ).text
    payloads = [
        json.loads(line[6:])["payload"] for line in text.splitlines() if line.startswith("data: ")
    ]
    assert {"from": "RUN_READ_TOOLS", "to": "CLASSIFY_REQUEST"} in payloads


async def test_finished_or_waiting_investigations_are_never_rerun(client: AsyncClient) -> None:
    u = await register(client)
    for state in ("COMPLETED", "PARTIAL", "AWAITING_PARAMETERS"):
        inv_id = await start(client, ws_headers(u), service="orders-api", **window())
        await _age(inv_id, state, minutes=600)
        async with get_sessionmaker()() as db:
            assert await claim_investigation(db, uuid.UUID(inv_id)) is False


async def test_reaper_fails_stuck_and_requeues_lost_investigations(client: AsyncClient) -> None:
    from app.documents import storage

    u = await register(client)
    stuck = await start(client, ws_headers(u), service="orders-api", **window())
    lost = await start(client, ws_headers(u), service="orders-api", **window())
    fresh = await start(client, ws_headers(u), service="orders-api", **window())
    await _age(stuck, "ANALYZE_HYPOTHESES", minutes=60)
    await _age(lost, "RECEIVED", minutes=30)
    await _age(fresh, "RUN_READ_TOOLS", minutes=1)
    url = storage.sqs().get_queue_url(QueueName="opspilot-investigate-test")["QueueUrl"]
    storage.sqs().purge_queue(QueueUrl=url)
    async with get_sessionmaker()() as db:
        counts = await reap(db)
    assert counts["investigations_failed"] == 1 and counts["investigations_requeued"] == 1
    s = (await client.get(f"{API}/investigations/{stuck}", headers=ws_headers(u))).json()
    assert s["state"] == "PARTIAL" and "worker stopped" in s["error"]
    assert (await client.get(f"{API}/investigations/{fresh}", headers=ws_headers(u))).json()[
        "state"
    ] == "RUN_READ_TOOLS"
    msgs = await storage.receive("opspilot-investigate-test", wait_seconds=1, max_messages=10)
    assert [m for m in msgs if lost in m["Body"]]


async def test_evaluation_runs_once_and_stale_runs_are_failed(client: AsyncClient) -> None:
    u = await register(client)
    r = await client.post(
        f"{API}/evaluations/run", headers=ws_headers(u), json={"config_label": "A_lexical"}
    )
    run_id = uuid.UUID(r.json()["id"])
    async with get_sessionmaker()() as db:
        done = await run_retrieval(
            db,
            RETRIEVAL_CONFIGS["A_lexical"],
            embedder=HashingEmbeddings(),
            dataset=load_dataset("v1"),
            run_id=run_id,
        )
        assert done.status == "completed"
        try:  # a duplicate message for the same run must not execute it again
            await run_retrieval(
                db,
                RETRIEVAL_CONFIGS["A_lexical"],
                embedder=HashingEmbeddings(),
                dataset=load_dataset("v1"),
                run_id=run_id,
            )
            raise AssertionError("duplicate run executed")
        except AlreadyClaimed:
            pass
        stale = EvaluationRun(
            dataset_name="x",
            dataset_version="v1",
            dataset_hash="h",
            kind="retrieval",
            config_label="B_vector",
            config={},
            split="test",
            status="running",
            started_at=datetime.now(UTC) - timedelta(hours=5),
        )
        db.add(stale)
        await db.commit()
        assert (await reap(db))["evaluations_failed"] == 1
        await db.refresh(stale)
        assert stale.status == "failed" and "No progress" in (stale.error or "")
        assert await claim_evaluation(db, stale.id) is False  # failed runs are never claimed


async def test_worker_skips_duplicate_evaluation_message(client: AsyncClient) -> None:
    from app import worker

    u = await register(client)
    r = await client.post(
        f"{API}/evaluations/run", headers=ws_headers(u), json={"config_label": "A_lexical"}
    )
    run_id = r.json()["id"]
    async with get_sessionmaker()() as db:
        assert await claim_evaluation(db, uuid.UUID(run_id))  # another worker has it
    await worker.handle_evaluation(
        {"run_id": run_id, "config_label": "A_lexical", "dataset_version": "v1"}
    )
    detail = (await client.get(f"{API}/evaluations/runs/{run_id}", headers=ws_headers(u))).json()
    assert detail["status"] == "running" and detail["error"] is None  # untouched, not marked failed
