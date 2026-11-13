"""Semantic retrieval: cosine distance over pgvector (HNSW index)."""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.rag.lexical.postgres_fts import apply_filters, to_candidate
from app.rag.types import Candidate, SearchFilters


async def vector_search(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query_vector: list[float],
    filters: SearchFilters,
    limit: int,
    embedding_model: str,
) -> list[Candidate]:
    # Higher ef_search keeps recall up when workspace filters prune HNSW results.
    await db.execute(text("SET LOCAL hnsw.ef_search = 200"))
    distance = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")
    q = (
        select(DocumentChunk, Document, distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.embedding.is_not(None))
        # never compare vectors from different embedding models
        .where(DocumentChunk.embedding_model == embedding_model)
    )
    q = apply_filters(q, workspace_id, filters).order_by(distance).limit(limit)
    out = []
    for i, (chunk, doc, dist) in enumerate((await db.execute(q)).all(), start=1):
        c = to_candidate(chunk, doc)
        c.vector_rank, c.vector_distance = i, float(dist)
        out.append(c)
    return out
