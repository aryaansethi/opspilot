"""Search (lexical / vector / hybrid), debug ranks, and grounded Q&A."""

import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.auth.deps import DB, Workspace, limit_user
from app.core.config import get_settings
from app.core.errors import AppError, Forbidden
from app.rag.embeddings.provider import get_embedding_provider
from app.rag.generation.grounded import generate_grounded_answer
from app.rag.generation.llm import LLMError, get_llm
from app.rag.lexical.postgres_fts import NAME as LEXICAL_NAME
from app.rag.pipeline import hybrid_search
from app.rag.reranking.reranker import (
    CrossEncoderReranker,
    Reranker,
    default_reranker,
    rerank_available,
)
from app.rag.types import Candidate, SearchFilters

router = APIRouter(tags=["search"])


class FiltersIn(BaseModel):
    source_types: list[Literal["runbook", "architecture", "incident_report", "other"]] = []
    services: list[str] = []
    environments: list[str] = []

    def to_filters(self) -> SearchFilters:
        return SearchFilters(
            tuple(self.source_types), tuple(self.services), tuple(self.environments)
        )


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    filters: FiltersIn = FiltersIn()
    top_k: int = Field(default=10, ge=1, le=50)
    mode: Literal["hybrid", "lexical", "vector"] = "hybrid"
    rerank: bool | None = None  # None → server default (RERANK_ENABLED)


class DebugInfo(BaseModel):
    lexical_rank: int | None
    vector_rank: int | None
    rrf_score: float
    rerank_score: float | None
    lexical_score: float | None
    vector_distance: float | None


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source_type: str
    excerpt: str
    section_path: str | None
    page_start: int | None
    page_end: int | None
    score: float
    debug: DebugInfo | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    latency_ms: float
    config: dict[str, Any]
    timings_ms: dict[str, float] | None = None


def _reranker(requested: bool | None) -> Reranker | None:
    if requested is None:
        return default_reranker()
    if requested and not rerank_available():
        raise AppError("Reranking is not installed on this server (uv sync --group rerank)")
    return CrossEncoderReranker(get_settings().rerank_model) if requested else None


def _result(c: Candidate, debug: bool) -> SearchResult:
    return SearchResult(
        chunk_id=c.chunk_id,
        document_id=c.document_id,
        document_title=c.document_title,
        source_type=c.source_type,
        excerpt=c.content[:1200],
        section_path=c.section_path,
        page_start=c.page_start,
        page_end=c.page_end,
        score=c.rerank_score if c.rerank_score is not None else c.rrf_score,
        debug=DebugInfo(
            lexical_rank=c.lexical_rank,
            vector_rank=c.vector_rank,
            rrf_score=c.rrf_score,
            rerank_score=c.rerank_score,
            lexical_score=c.lexical_score,
            vector_distance=c.vector_distance,
        )
        if debug
        else None,
    )


async def _run(body: SearchRequest, db: DB, ctx: Workspace, debug: bool) -> SearchResponse:
    s = get_settings()
    reranker = _reranker(body.rerank)
    embedder = get_embedding_provider()
    out = await hybrid_search(
        db,
        ctx.workspace_id,
        body.query,
        embedder=embedder,
        reranker=reranker,
        filters=body.filters.to_filters(),
        mode=body.mode,
        top_k=body.top_k,
    )
    return SearchResponse(
        results=[_result(c, debug) for c in out.results],
        latency_ms=round(out.latency_ms, 1),
        config={
            "mode": body.mode,
            "lexical": LEXICAL_NAME,
            "embedding_model": embedder.model,
            "rrf_k": s.rrf_k,
            "reranker": reranker.name if reranker else None,
        },
        timings_ms={k: round(v, 1) for k, v in out.timings_ms.items()},
    )


@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest, db: DB, ctx: Workspace) -> SearchResponse:
    return await _run(body, db, ctx, debug=False)


@router.post("/search/debug", response_model=SearchResponse)
async def search_debug(body: SearchRequest, db: DB, ctx: Workspace) -> SearchResponse:
    if get_settings().environment == "production" and ctx.role != "owner":
        raise Forbidden("Debug search is restricted to workspace owners")
    return await _run(body, db, ctx, debug=True)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    filters: FiltersIn = FiltersIn()
    rerank: bool | None = None


class EvidenceOut(BaseModel):
    id: uuid.UUID
    source_system: Literal["knowledge_base"] = "knowledge_base"
    title: str
    source_reference: str
    excerpt: str
    retrieval_method: str
    rank: int
    metadata: dict[str, Any]


class ClaimOut(BaseModel):
    text: str
    evidence_ids: list[uuid.UUID]


class AskResponse(BaseModel):
    answer: str
    claims: list[ClaimOut]
    citations: list[EvidenceOut]
    insufficient_evidence: bool
    model: str | None
    retrieved_count: int
    removed_invalid_citations: list[str]
    latency_ms: float  # whole request: retrieval + generation
    retrieval_ms: float
    generation_ms: float


@router.post(
    "/ask",
    response_model=AskResponse,
    dependencies=[limit_user("ask", get_settings().ask_rate_limit_per_minute, 60)],
)
async def ask(body: AskRequest, db: DB, ctx: Workspace) -> AskResponse:
    s = get_settings()
    started = time.perf_counter()
    out = await hybrid_search(
        db,
        ctx.workspace_id,
        body.question,
        embedder=get_embedding_provider(),
        reranker=_reranker(body.rerank),
        filters=body.filters.to_filters(),
        top_k=s.answer_context_chunks,
    )
    t_gen = time.perf_counter()
    try:
        g = await generate_grounded_answer(get_llm(), body.question, out.results)
    except LLMError as e:
        raise AppError(f"The language model returned an unusable answer: {e}") from e
    ranks = {c.chunk_id: i for i, c in enumerate(out.results, start=1)}
    return AskResponse(
        answer=g.answer,
        claims=[
            ClaimOut(text=c.text, evidence_ids=[e.chunk_id for e in c.evidence]) for c in g.claims
        ],
        citations=[
            EvidenceOut(
                id=c.chunk_id,
                title=c.document_title,
                source_reference=f"document:{c.document_id}#chunk:{c.chunk_id}",
                excerpt=c.content[:800],
                retrieval_method="hybrid_rrf" + ("+rerank" if c.rerank_score is not None else ""),
                rank=ranks[c.chunk_id],
                metadata={
                    "document_id": str(c.document_id),
                    "section_path": c.section_path,
                    "page_start": c.page_start,
                    "page_end": c.page_end,
                    "source_type": c.source_type,
                },
            )
            for c in g.citations
        ],
        insufficient_evidence=g.insufficient_evidence,
        model=g.model,
        retrieved_count=len(out.results),
        removed_invalid_citations=g.removed_labels,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        retrieval_ms=round(out.latency_ms, 1),
        generation_ms=round((time.perf_counter() - t_gen) * 1000, 1),
    )
