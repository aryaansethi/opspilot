"""Lexical retrieval with PostgreSQL full-text search.

This is NOT BM25: ranking is `ts_rank_cd` (cover density) over an English
tsvector with section headings weighted above body text. Query terms are OR-ed
so natural-language questions still match partially; more matching terms rank
higher. A genuine BM25 engine (OpenSearch) can implement the same interface.
"""

import uuid

from sqlalchemy import Select, Text, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentChunk
from app.rag.types import Candidate, SearchFilters

NAME = "postgres_fts_ts_rank_cd"


def apply_filters(q: Select, workspace_id: uuid.UUID, f: SearchFilters) -> Select:  # type: ignore[type-arg]
    q = q.where(
        DocumentChunk.workspace_id == workspace_id,
        Document.workspace_id == workspace_id,
        Document.status == "indexed",
    )
    if f.source_types:
        q = q.where(Document.source_type.in_(f.source_types))
    if f.services:
        q = q.where(Document.service.in_(f.services))
    if f.environments:
        q = q.where(Document.environment.in_(f.environments))
    return q


def to_candidate(chunk: DocumentChunk, doc: Document) -> Candidate:
    return Candidate(
        chunk_id=chunk.id,
        document_id=doc.id,
        document_title=doc.title,
        source_type=doc.source_type,
        content=chunk.content,
        section_path=chunk.section_path,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
    )


async def lexical_search(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query: str,
    filters: SearchFilters,
    limit: int,
    *,
    match_all: bool = False,
) -> list[Candidate]:
    """match_all=False: any query term may match (OR). True: every term must match (AND)."""
    plain = func.plainto_tsquery("english", query)
    tsq = (
        plain
        if match_all
        else func.to_tsquery("english", func.replace(cast(plain, Text), "&", "|"))
    )
    rank = func.ts_rank_cd(DocumentChunk.tsv, tsq, 32).label("rank")  # 32: rank/(rank+1)
    q = (
        select(DocumentChunk, Document, rank)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.tsv.op("@@")(tsq))
    )
    # Ties are common with ts_rank_cd. Break them by content, not by random UUIDs, so the same
    # corpus ranks identically in every database (reproducible evaluation).
    q = (
        apply_filters(q, workspace_id, filters)
        .order_by(rank.desc(), DocumentChunk.content_hash, DocumentChunk.chunk_index)
        .limit(limit)
    )
    out = []
    for i, (chunk, doc, score) in enumerate((await db.execute(q)).all(), start=1):
        c = to_candidate(chunk, doc)
        c.lexical_rank, c.lexical_score = i, float(score)
        out.append(c)
    return out
