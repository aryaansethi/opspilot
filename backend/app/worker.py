"""Ingestion worker: long-polls SQS and indexes documents.

Run: `uv run python -m app.worker`
- Success or permanent failure → message deleted.
- Transient failure → message left on the queue; SQS redelivers after the
  visibility timeout and moves it to the DLQ after 3 receives.
"""

import asyncio
import json
import signal
import uuid

from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.session import dispose_engine, get_sessionmaker
from app.documents import storage
from app.documents.ingestion import ingest_document
from app.rag.embeddings.provider import get_embedding_provider


async def handle(body: dict[str, object]) -> None:
    async with get_sessionmaker()() as db:
        await ingest_document(
            db,
            uuid.UUID(str(body["document_id"])),
            get_embedding_provider(),
            force=bool(body.get("force", False)),
        )


async def run(stop: asyncio.Event) -> None:
    queue = get_settings().sqs_ingest_queue
    log.info("worker.started", queue=queue)
    while not stop.is_set():
        try:
            messages = await storage.receive(queue, wait_seconds=10)
        except Exception as e:  # noqa: BLE001
            log.error("worker.receive_failed", error=str(e))
            await asyncio.sleep(5)
            continue
        for msg in messages:
            try:
                await handle(json.loads(msg["Body"]))
                await storage.ack(queue, msg["ReceiptHandle"])
            except Exception as e:  # noqa: BLE001
                log.error("worker.message_failed", error=repr(e), message_id=msg.get("MessageId"))
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
