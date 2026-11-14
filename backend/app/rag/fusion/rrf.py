"""Reciprocal Rank Fusion: RRF(d) = Σ_i 1 / (k + rank_i(d)).

The result is a fusion score for ordering, not a probability of relevance.
"""

import uuid

from app.rag.types import Candidate


def reciprocal_rank_fusion(
    lexical: list[Candidate], vector: list[Candidate], k: int = 60
) -> list[Candidate]:
    merged: dict[uuid.UUID, Candidate] = {}
    for c in lexical:
        merged[c.chunk_id] = c
        c.rrf_score = 1.0 / (k + (c.lexical_rank or 0))
    for c in vector:
        existing = merged.get(c.chunk_id)
        if existing is None:
            merged[c.chunk_id] = c
            c.rrf_score = 1.0 / (k + (c.vector_rank or 0))
        else:
            existing.vector_rank, existing.vector_distance = c.vector_rank, c.vector_distance
            existing.rrf_score += 1.0 / (k + (c.vector_rank or 0))
    # Equal scores are ordered by content, never by random ids, so rankings reproduce across DBs.
    return sorted(
        merged.values(),
        key=lambda c: (-c.rrf_score, c.document_title, c.char_start, c.content),
    )


def dedupe_overlapping(candidates: list[Candidate], min_overlap: float = 0.5) -> list[Candidate]:
    """Drop a chunk if a higher-ranked chunk of the same document covers most of it."""
    kept: list[Candidate] = []
    for c in candidates:
        length = max(1, c.char_end - c.char_start)
        dup = False
        for k in kept:
            if k.document_id != c.document_id:
                continue
            overlap = min(k.char_end, c.char_end) - max(k.char_start, c.char_start)
            if overlap / length >= min_overlap:
                dup = True
                break
        if not dup:
            kept.append(c)
    return kept
