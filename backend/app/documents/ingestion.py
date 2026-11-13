"""Worker-side ingestion: download → validate → parse → chunk → embed → index.

Idempotent: if the file's content hash matches what is already indexed, the
document is left untouched.
"""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.documents import storage
from app.models import Document, DocumentChunk, DocumentIngestionJob
from app.rag.chunking.chunker import chunk_document
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.ingestion.parsers import UnsupportedDocument, parse


class PermanentIngestionError(Exception):
    pass


async def ingest_document(
    db: AsyncSession, document_id: uuid.UUID, embedder: EmbeddingProvider, *, force: bool = False
) -> str:
    """Returns the final status. Raises on transient errors (caller decides on retry)."""
    s = get_settings()
    doc = await db.get(Document, document_id)
    if doc is None:
        log.warning("ingest.document_missing", document_id=str(document_id))
        return "missing"

    job = await db.scalar(
        select(DocumentIngestionJob)
        .where(DocumentIngestionJob.document_id == doc.id)
        .order_by(DocumentIngestionJob.created_at.desc())
        .limit(1)
    )
    if job is None:
        job = DocumentIngestionJob(workspace_id=doc.workspace_id, document_id=doc.id)
        db.add(job)
    job.attempt += 1
    job.status = "processing"
    job.started_at = datetime.now(UTC)
    doc.status = "processing"
    doc.error = None
    await db.commit()

    try:
        data = await storage.get_object_bytes(doc.s3_key, s.max_upload_bytes)
        file_hash = hashlib.sha256(data).hexdigest()
        if not force and doc.content_hash == file_hash and doc.chunk_count > 0:
            doc.status, job.status = "indexed", "skipped_unchanged"
            job.finished_at = datetime.now(UTC)
            await db.commit()
            return "indexed"

        try:
            parsed = parse(data, doc.mime_type)
        except UnsupportedDocument as e:
            raise PermanentIngestionError(str(e)) from e
        chunks = chunk_document(parsed, s.chunk_target_tokens, s.chunk_overlap_tokens)
        if not chunks:
            raise PermanentIngestionError("No indexable content found")
        vectors = await embedder.embed([c.content for c in chunks])

        await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        db.add_all(
            DocumentChunk(
                workspace_id=doc.workspace_id,
                document_id=doc.id,
                chunk_index=c.index,
                content=c.content,
                section_path=c.section_path,
                page_start=c.page_start,
                page_end=c.page_end,
                char_start=c.char_start,
                char_end=c.char_end,
                token_estimate=c.token_estimate,
                content_hash=c.content_hash,
                embedding=v,
                embedding_model=embedder.model,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        now = datetime.now(UTC)
        doc.content_hash = file_hash
        doc.chunk_count = len(chunks)
        doc.embedding_model = embedder.model
        doc.indexed_at = now
        doc.status = job.status = "indexed"
        job.finished_at = now
        await db.commit()
        log.info("ingest.indexed", document_id=str(doc.id), chunks=len(chunks))
        return "indexed"
    except PermanentIngestionError as e:
        await db.rollback()
        await _mark_failed(db, doc.id, job.id, str(e))
        return "failed"
    except Exception as e:
        await db.rollback()
        await _mark_failed(db, doc.id, job.id, f"Transient error, will retry: {type(e).__name__}")
        raise


async def _mark_failed(db: AsyncSession, doc_id: uuid.UUID, job_id: uuid.UUID, error: str) -> None:
    doc = await db.get(Document, doc_id)
    job = await db.get(DocumentIngestionJob, job_id)
    if doc:
        doc.status, doc.error = "failed", error
    if job:
        job.status, job.error, job.finished_at = "failed", error, datetime.now(UTC)
    await db.commit()
    log.warning("ingest.failed", document_id=str(doc_id), error=error)
