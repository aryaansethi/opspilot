"""Hybrid retrieval pipeline: filters → lexical ∥ vector → RRF → dedupe → rerank."""

import time
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.fusion.rrf import dedupe_overlapping, reciprocal_rank_fusion
from app.rag.lexical.postgres_fts import lexical_search
from app.rag.reranking.reranker import Reranker
from app.rag.types import Candidate, SearchFilters
from app.rag.vector.pgvector_search import vector_search

Mode = Literal["hybrid", "lexical", "vector"]


@dataclass
class SearchOutcome:
    results: list[Candidate]
    latency_ms: float
    timings_ms: dict[str, float]


async def hybrid_search(
    db: AsyncSession,
    workspace_id: uuid.UUID,
    query: str,
    *,
    embedder: EmbeddingProvider,
    reranker: Reranker | None = None,
    filters: SearchFilters | None = None,
    mode: Mode = "hybrid",
    top_k: int = 10,
) -> SearchOutcome:
    s = get_settings()
    filters = filters or SearchFilters()
    query = " ".join(query.split())  # normalise whitespace only; keep identifiers intact
    timings: dict[str, float] = {}
    t0 = time.perf_counter()

    lexical: list[Candidate] = []
    vector: list[Candidate] = []
    if mode in ("hybrid", "lexical"):
        t = time.perf_counter()
        lexical = await lexical_search(db, workspace_id, query, filters, s.retrieval_candidates)
        timings["lexical"] = (time.perf_counter() - t) * 1000
    if mode in ("hybrid", "vector"):
        t = time.perf_counter()
        [qvec] = await embedder.embed([query])
        timings["embed_query"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        vector = await vector_search(
            db, workspace_id, qvec, filters, s.retrieval_candidates, embedder.model
        )
        timings["vector"] = (time.perf_counter() - t) * 1000

    fused = dedupe_overlapping(reciprocal_rank_fusion(lexical, vector, k=s.rrf_k))
    if reranker is not None and fused:
        t = time.perf_counter()
        head = await reranker.rerank(query, fused[: s.rerank_candidates])
        fused = head + fused[s.rerank_candidates :]
        timings["rerank"] = (time.perf_counter() - t) * 1000

    return SearchOutcome(fused[:top_k], (time.perf_counter() - t0) * 1000, timings)
