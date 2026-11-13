"""Knowledge-base document endpoints (all workspace-scoped)."""

import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Query, status
from sqlalchemy import and_, or_, select

from app.audit.service import record
from app.auth.deps import DB, Workspace
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound
from app.documents import storage
from app.documents.schemas import (
    ChunkOut,
    CompleteUploadRequest,
    DocumentOut,
    DocumentStatus,
    Page,
    UploadUrlRequest,
    UploadUrlResponse,
)
from app.models import Document, DocumentChunk, DocumentIngestionJob
from app.rag.ingestion.parsers import mime_allowed

router = APIRouter(prefix="/documents", tags=["documents"])


async def _get_doc(db: DB, ctx: Workspace, document_id: uuid.UUID) -> Document:
    doc = await db.scalar(
        select(Document).where(
            Document.id == document_id, Document.workspace_id == ctx.workspace_id
        )
    )
    if doc is None:
        raise NotFound("Document not found")
    return doc


async def _enqueue(db: DB, doc: Document, force: bool = False) -> None:
    doc.status, doc.error = "queued", None
    db.add(DocumentIngestionJob(workspace_id=doc.workspace_id, document_id=doc.id))
    await db.commit()
    await storage.enqueue(
        get_settings().sqs_ingest_queue,
        {"document_id": str(doc.id), "workspace_id": str(doc.workspace_id), "force": force},
    )


@router.post("/upload-url", response_model=UploadUrlResponse, status_code=status.HTTP_201_CREATED)
async def upload_url(body: UploadUrlRequest, db: DB, ctx: Workspace) -> UploadUrlResponse:
    ctx.require_write()
    s = get_settings()
    if not mime_allowed(body.mime_type, body.filename):
        raise AppError("File extension does not match an allowed type (.pdf, .md, .txt)")
    if body.size_bytes > s.max_upload_bytes:
        raise AppError(f"File exceeds {s.max_upload_bytes // (1024 * 1024)} MB limit")
    doc_id = uuid.uuid4()
    key = f"ws/{ctx.workspace_id}/docs/{doc_id}/{body.filename}"
    doc = Document(
        id=doc_id,
        workspace_id=ctx.workspace_id,
        title=body.title or body.filename.rsplit(".", 1)[0],
        filename=body.filename,
        source_type=body.source_type,
        service=body.service,
        environment=body.environment,
        s3_key=key,
        mime_type=body.mime_type,
        size_bytes=body.size_bytes,
        status="pending_upload",
        created_by=ctx.user.id,
    )
    db.add(doc)
    await db.commit()
    return UploadUrlResponse(
        document_id=doc_id,
        upload_url=await storage.presign_put(key, body.mime_type),
        headers={"Content-Type": body.mime_type},
    )


@router.post("/complete-upload", response_model=DocumentOut)
async def complete_upload(body: CompleteUploadRequest, db: DB, ctx: Workspace) -> Document:
    ctx.require_write()
    doc = await _get_doc(db, ctx, body.document_id)
    if doc.status != "pending_upload":
        raise Conflict(f"Document is already {doc.status}")
    head = await storage.head_object(doc.s3_key)
    if head is None:
        raise AppError("Upload not found in storage; PUT the file to upload_url first")
    size = int(head["ContentLength"])
    if size > get_settings().max_upload_bytes:
        await storage.delete_object(doc.s3_key)
        raise AppError("Uploaded file exceeds the size limit")
    doc.size_bytes = size
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="document.uploaded",
        target_type="document",
        target_id=doc.id,
        metadata={"filename": doc.filename, "size_bytes": size},
    )
    await _enqueue(db, doc)
    return doc


def _encode_cursor(doc: Document) -> str:
    return base64.urlsafe_b64encode(f"{doc.created_at.isoformat()}|{doc.id}".encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, ident = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(ident)
    except Exception:  # noqa: BLE001
        raise AppError("Invalid cursor") from None


@router.get("", response_model=Page[DocumentOut])
async def list_documents(
    db: DB,
    ctx: Workspace,
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = None,
    service: str | None = None,
) -> Page[DocumentOut]:
    q = select(Document).where(Document.workspace_id == ctx.workspace_id)
    if status_filter:
        q = q.where(Document.status == status_filter)
    if source_type:
        q = q.where(Document.source_type == source_type)
    if service:
        q = q.where(Document.service == service)
    if cursor:
        ts, ident = _decode_cursor(cursor)
        q = q.where(
            or_(Document.created_at < ts, and_(Document.created_at == ts, Document.id < ident))
        )
    rows = list(
        await db.scalars(
            q.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    return Page[DocumentOut](
        items=[DocumentOut.model_validate(r) for r in rows],
        next_cursor=_encode_cursor(rows[-1]) if has_more else None,
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, db: DB, ctx: Workspace) -> Document:
    return await _get_doc(db, ctx, document_id)


@router.get("/{document_id}/status", response_model=DocumentStatus)
async def get_status(document_id: uuid.UUID, db: DB, ctx: Workspace) -> Document:
    return await _get_doc(db, ctx, document_id)


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
async def get_chunks(document_id: uuid.UUID, db: DB, ctx: Workspace) -> list[DocumentChunk]:
    doc = await _get_doc(db, ctx, document_id)
    rows = await db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == doc.id, DocumentChunk.workspace_id == ctx.workspace_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(rows)


@router.post("/{document_id}/reindex", response_model=DocumentOut)
async def reindex(document_id: uuid.UUID, db: DB, ctx: Workspace) -> Document:
    ctx.require_write()
    doc = await _get_doc(db, ctx, document_id)
    if doc.status in ("pending_upload", "queued", "processing"):
        raise Conflict(f"Document is {doc.status}; wait for it to finish")
    await _enqueue(db, doc, force=True)
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: uuid.UUID, db: DB, ctx: Workspace) -> None:
    ctx.require_write()
    doc = await _get_doc(db, ctx, document_id)
    key, title = doc.s3_key, doc.title
    await db.delete(doc)  # chunks + jobs cascade
    record(
        db,
        workspace_id=ctx.workspace_id,
        actor_user_id=ctx.user.id,
        action="document.deleted",
        target_type="document",
        target_id=document_id,
        metadata={"title": title},
    )
    await db.commit()
    await storage.delete_object(key)
