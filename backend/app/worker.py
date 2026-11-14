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
from app.evaluations.runner import RETRIEVAL_CONFIGS, run_answers, run_retrieval
from app.investigations.engine import run_investigation
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
    run_id = uuid.UUID(str(body["run_id"]))
    label = str(body["config_label"])
    split = str(body.get("split", "test"))
    async with get_sessionmaker()() as db:
        if label in RETRIEVAL_CONFIGS:
            await run_retrieval(
                db,
                RETRIEVAL_CONFIGS[label],
                embedder=get_embedding_provider(),
                split=split,
                run_id=run_id,
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
                )


async def run(stop: asyncio.Event) -> None:
    s = get_settings()
    await asyncio.gather(
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
