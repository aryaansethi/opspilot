"""Background worker: document ingestion and investigation runs.

Run: `uv run python -m app.worker`
Both queues are long-polled concurrently, so a slow investigation never blocks
ingestion. Success or permanent failure deletes the message; a crash leaves it
on the queue for SQS to redeliver (and eventually move to the DLQ).
"""

import asyncio
import json
import signal
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.session import dispose_engine, get_sessionmaker
from app.documents import storage
from app.documents.ingestion import ingest_document
from app.evaluations.extra import run_injection, run_tool_selection
from app.evaluations.runner import (
    RETRIEVAL_CONFIGS,
    load_dataset,
    mark_run_failed,
    run_answers,
    run_retrieval,
)
from app.investigations.engine import run_investigation
from app.jobs import AlreadyClaimed, reap
from app.rag.embeddings.provider import get_embedding_provider
from app.rag.generation.llm import get_llm


async def handle_ingest(body: dict[str, Any]) -> None:
    async with get_sessionmaker()() as db:
        await ingest_document(
            db,
            uuid.UUID(str(body["document_id"])),
            get_embedding_provider(),
            force=bool(body.get("force", False)),
        )


async def handle_investigation(body: dict[str, Any]) -> None:
    async with get_sessionmaker()() as db:
        await run_investigation(
            db,
            uuid.UUID(str(body["investigation_id"])),
            llm=get_llm(),
            embedder=get_embedding_provider(),
        )


async def handle_evaluation(body: dict[str, Any]) -> None:
    """Never leaves a run in "running": any failure is recorded on the run and the message is
    acknowledged (an evaluation retried hours later would be confusing, not helpful)."""
    run_id = uuid.UUID(str(body["run_id"]))
    try:
        await _run_evaluation(body, run_id)
    except AlreadyClaimed:
        log.info("worker.evaluation_duplicate_skipped", run_id=str(run_id))
    except Exception as e:  # noqa: BLE001
        log.error("worker.evaluation_failed", run_id=str(run_id), error=repr(e), exc_info=e)
        await mark_run_failed(run_id, e)


async def _run_evaluation(body: dict[str, Any], run_id: uuid.UUID) -> None:
    label = str(body["config_label"])
    split = str(body.get("split", "test"))
    dataset = load_dataset(body.get("dataset_version"))  # older messages: default version
    async with get_sessionmaker()() as db:
        if label in RETRIEVAL_CONFIGS:
            await run_retrieval(
                db,
                RETRIEVAL_CONFIGS[label],
                embedder=get_embedding_provider(),
                split=split,
                run_id=run_id,
                dataset=dataset,
            )
        elif label == "tool_selection_planner":
            await run_tool_selection(db, llm=get_llm(), dataset=dataset, run_id=run_id)
        elif label == "injection_resistance":
            await run_injection(
                db, llm=get_llm(), embedder=get_embedding_provider(), dataset=dataset, run_id=run_id
            )
        else:
            limit = body.get("limit")
            await run_answers(
                db,
                embedder=get_embedding_provider(),
                llm=get_llm(),
                split=split,
                run_id=run_id,
                limit=int(limit) if limit else None,
                dataset=dataset,
            )


async def consume(
    queue: str, handler: Callable[[dict[str, Any]], Awaitable[None]], stop: asyncio.Event
) -> None:
    log.info("worker.consuming", queue=queue)
    while not stop.is_set():
        try:
            messages = await storage.receive(queue, wait_seconds=10)
        except Exception as e:  # noqa: BLE001
            log.error("worker.receive_failed", queue=queue, error=str(e))
            await asyncio.sleep(5)
            continue
        for msg in messages:
            try:
                await handler(json.loads(msg["Body"]))
                await storage.ack(queue, msg["ReceiptHandle"])
            except Exception as e:  # noqa: BLE001
                log.error(
                    "worker.message_failed",
                    queue=queue,
                    error=repr(e),
                    message_id=msg.get("MessageId"),
                    exc_info=e,
                )


async def reaper(stop: asyncio.Event, interval_seconds: float = 300) -> None:
    """Periodically mark stuck jobs (see app/jobs.py)."""
    while not stop.is_set():
        try:
            async with get_sessionmaker()() as db:
                await reap(db)
        except Exception as e:  # noqa: BLE001
            log.error("worker.reaper_failed", error=repr(e), exc_info=e)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass


async def run(stop: asyncio.Event) -> None:
    s = get_settings()
    await asyncio.gather(
        reaper(stop),
        consume(s.sqs_ingest_queue, handle_ingest, stop),
        consume(s.sqs_investigate_queue, handle_investigation, stop),
        consume(s.sqs_evaluate_queue, handle_evaluation, stop),
    )
    await dispose_engine()
    log.info("worker.stopped")


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level, json=s.environment == "production")
    stop = asyncio.Event()
    loop = asyncio.new_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    loop.run_until_complete(run(stop))


if __name__ == "__main__":
    main()
