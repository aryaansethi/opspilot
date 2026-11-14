"""Hybrid retrieval pipeline: filters → lexical ∥ vector → RRF → dedupe → rerank."""

import time
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.fusion.rrf import dedupe_overlapping, reciprocal_rank_fusion, weighted_rrf
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
    lexical_weight: float | None = None,
    lexical_depth: int | None = None,
    query_vector: list[float] | None = None,
) -> SearchOutcome:
    """lexical_weight / lexical_depth default to the tuned settings (fusion_lexical_*); pass
    1.0 and retrieval_candidates for standard equal-weight RRF. query_vector skips re-embedding
    when the caller already has the embedding of the same query."""
    s = get_settings()
    w_lex = s.fusion_lexical_weight if lexical_weight is None else lexical_weight
    depth = s.fusion_lexical_depth if lexical_depth is None else lexical_depth
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
        if query_vector is not None:
            qvec = query_vector
        else:
            [qvec] = await embedder.embed([query])
            timings["embed_query"] = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        vector = await vector_search(
            db, workspace_id, qvec, filters, s.retrieval_candidates, embedder.model
        )
        timings["vector"] = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    if mode == "hybrid":
        fused = dedupe_overlapping(
            weighted_rrf(
                lexical[:depth], vector, k=s.rrf_k, lexical_weight=w_lex, vector_weight=1.0
            )
        )
    else:  # single list: RRF just orders by that list's rank
        fused = dedupe_overlapping(reciprocal_rank_fusion(lexical, vector, k=s.rrf_k))
    timings["fusion"] = (time.perf_counter() - t) * 1000
    if reranker is not None and fused:
        t = time.perf_counter()
        head = await reranker.rerank(query, fused[: s.rerank_candidates])
        fused = head + fused[s.rerank_candidates :]
        timings["rerank"] = (time.perf_counter() - t) * 1000

    total = (time.perf_counter() - t0) * 1000
    timings["total"] = total
    return SearchOutcome(fused[:top_k], total, timings)
