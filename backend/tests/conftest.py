"""Integration test fixtures. Requires `docker compose up -d` (postgres on :5433).

Tests run against the separate `opspilot_test` database, migrated to head once
per session and truncated between tests.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://opspilot:opspilot@localhost:5433/opspilot_test"
os.environ["ENVIRONMENT"] = "test"
os.environ["SQS_INGEST_QUEUE"] = "opspilot-ingest-test"
os.environ["S3_DOCUMENTS_BUCKET"] = "opspilot-documents-test"

from collections.abc import AsyncIterator  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db.session import dispose_engine, get_engine  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _aws_resources() -> None:
    from app.documents import storage

    storage.s3().create_bucket(Bucket="opspilot-documents-test")
    url = storage.sqs().create_queue(QueueName="opspilot-ingest-test")["QueueUrl"]
    storage.sqs().purge_queue(QueueUrl=url)


@pytest.fixture(autouse=True)
def _fake_embeddings() -> object:
    from app.rag.embeddings.provider import HashingEmbeddings, set_embedding_provider

    set_embedding_provider(HashingEmbeddings())
    yield
    set_embedding_provider(None)


@pytest.fixture(autouse=True)
async def _clean_db() -> AsyncIterator[None]:
    yield
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session", autouse=True)
async def _dispose() -> AsyncIterator[None]:
    yield
    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c


async def register(client: AsyncClient, email: str = "alice@example.com") -> dict[str, Any]:
    r = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery", "display_name": email[:5]},
    )
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    ws = (await client.get("/api/v1/workspaces", headers=headers)).json()
    return {**body, "headers": headers, "workspace_id": ws[0]["id"]}
