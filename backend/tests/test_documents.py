"""End-to-end document flow against LocalStack S3/SQS and the test database."""

import json
import uuid
from typing import Any

import httpx
from httpx import AsyncClient

from app.db.session import get_sessionmaker
from app.documents import storage
from app.documents.ingestion import ingest_document
from app.rag.embeddings.provider import HashingEmbeddings
from tests.conftest import register

API = "/api/v1"
RUNBOOK = b"""# Payments API Runbook

## Connection pool exhaustion

When `HikariPool-1 - Connection is not available` appears, check pool size.

## Rollback

Roll back with the deploy pipeline.
"""


def ws_headers(u: dict[str, Any]) -> dict[str, str]:
    return {**u["headers"], "X-Workspace-Id": u["workspace_id"]}


async def upload(
    client: AsyncClient,
    u: dict[str, Any],
    data: bytes = RUNBOOK,
    name: str = "runbook.md",
    mime: str = "text/markdown",
) -> str:
    r = await client.post(
        f"{API}/documents/upload-url",
        headers=ws_headers(u),
        json={
            "filename": name,
            "mime_type": mime,
            "size_bytes": len(data),
            "source_type": "runbook",
            "service": "payments-api",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    async with httpx.AsyncClient() as raw:
        put = await raw.put(body["upload_url"], content=data, headers=body["headers"])
    assert put.status_code == 200, put.text
    done = await client.post(
        f"{API}/documents/complete-upload",
        headers=ws_headers(u),
        json={"document_id": body["document_id"]},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "queued"
    return str(body["document_id"])


async def drain_and_ingest() -> list[str]:
    msgs = await storage.receive("opspilot-ingest-test", wait_seconds=1, max_messages=10)
    statuses = []
    for m in msgs:
        body = json.loads(m["Body"])
        async with get_sessionmaker()() as db:
            statuses.append(
                await ingest_document(
                    db, uuid.UUID(body["document_id"]), HashingEmbeddings(), force=body["force"]
                )
            )
        await storage.ack("opspilot-ingest-test", m["ReceiptHandle"])
    return statuses


async def test_upload_ingest_and_read_chunks(client: AsyncClient) -> None:
    u = await register(client)
    doc_id = await upload(client, u)
    assert await drain_and_ingest() == ["indexed"]
    st = (await client.get(f"{API}/documents/{doc_id}/status", headers=ws_headers(u))).json()
    assert st["status"] == "indexed" and st["chunk_count"] >= 2
    chunks = (await client.get(f"{API}/documents/{doc_id}/chunks", headers=ws_headers(u))).json()
    assert {c["section_path"] for c in chunks} >= {
        "Payments API Runbook > Connection pool exhaustion",
        "Payments API Runbook > Rollback",
    }
    listing = (await client.get(f"{API}/documents", headers=ws_headers(u))).json()
    assert listing["items"][0]["id"] == doc_id and listing["next_cursor"] is None


async def test_reingest_unchanged_is_idempotent_and_reindex_forces(client: AsyncClient) -> None:
    u = await register(client)
    doc_id = await upload(client, u)
    await drain_and_ingest()
    async with get_sessionmaker()() as db:
        assert await ingest_document(db, uuid.UUID(doc_id), HashingEmbeddings()) == "indexed"
    r = await client.post(f"{API}/documents/{doc_id}/reindex", headers=ws_headers(u))
    assert r.status_code == 200 and r.json()["status"] == "queued"
    assert await drain_and_ingest() == ["indexed"]
    chunks = (await client.get(f"{API}/documents/{doc_id}/chunks", headers=ws_headers(u))).json()
    assert [c["chunk_index"] for c in chunks] == list(range(len(chunks)))


async def test_bad_pdf_fails_permanently_with_reason(client: AsyncClient) -> None:
    u = await register(client)
    doc_id = await upload(client, u, b"definitely not a pdf", "fake.pdf", "application/pdf")
    assert await drain_and_ingest() == ["failed"]
    st = (await client.get(f"{API}/documents/{doc_id}/status", headers=ws_headers(u))).json()
    assert st["status"] == "failed" and "not a valid PDF" in st["error"]


async def test_upload_validation(client: AsyncClient) -> None:
    u = await register(client)
    bad_ext = await client.post(
        f"{API}/documents/upload-url",
        headers=ws_headers(u),
        json={
            "filename": "x.exe",
            "mime_type": "text/plain",
            "size_bytes": 10,
            "source_type": "other",
        },
    )
    assert bad_ext.status_code == 400
    too_big = await client.post(
        f"{API}/documents/upload-url",
        headers=ws_headers(u),
        json={
            "filename": "x.txt",
            "mime_type": "text/plain",
            "size_bytes": 999_999_999,
            "source_type": "other",
        },
    )
    assert too_big.status_code == 400
    traversal = await client.post(
        f"{API}/documents/upload-url",
        headers=ws_headers(u),
        json={
            "filename": "../../etc/passwd.txt",
            "mime_type": "text/plain",
            "size_bytes": 10,
            "source_type": "other",
        },
    )
    assert traversal.status_code == 422
    # complete before uploading anything
    r = await client.post(
        f"{API}/documents/upload-url",
        headers=ws_headers(u),
        json={
            "filename": "y.txt",
            "mime_type": "text/plain",
            "size_bytes": 10,
            "source_type": "other",
        },
    )
    early = await client.post(
        f"{API}/documents/complete-upload",
        headers=ws_headers(u),
        json={"document_id": r.json()["document_id"]},
    )
    assert early.status_code == 400


async def test_documents_are_isolated_between_workspaces(client: AsyncClient) -> None:
    alice = await register(client, "alice@example.com")
    bob = await register(client, "bob@example.com")
    doc_id = await upload(client, alice)
    await drain_and_ingest()
    for path in ("", "/status", "/chunks"):
        r = await client.get(f"{API}/documents/{doc_id}{path}", headers=ws_headers(bob))
        assert r.status_code == 404
    assert (
        await client.delete(f"{API}/documents/{doc_id}", headers=ws_headers(bob))
    ).status_code == 404
    assert (await client.get(f"{API}/documents", headers=ws_headers(bob))).json()["items"] == []


async def test_delete_removes_rows_and_object(client: AsyncClient) -> None:
    u = await register(client)
    doc_id = await upload(client, u)
    await drain_and_ingest()
    r = await client.delete(f"{API}/documents/{doc_id}", headers=ws_headers(u))
    assert r.status_code == 204
    assert (await client.get(f"{API}/documents/{doc_id}", headers=ws_headers(u))).status_code == 404
    key = f"ws/{u['workspace_id']}/docs/{doc_id}/runbook.md"
    assert await storage.head_object(key) is None
