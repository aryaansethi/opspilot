"""Information-retrieval metrics with binary, section-level relevance.

A retrieved chunk is relevant if it comes from an expected document and its
section path ends with an expected section heading. Several chunks from the same
expected section get credit only once for recall/nDCG (but each counts for precision).
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Expected:
    document: str
    section: str


@dataclass(frozen=True)
class Retrieved:
    document: str
    section_path: str | None


def match(r: Retrieved, expected: list[Expected]) -> int | None:
    """Index of the expected section this chunk belongs to, or None."""
    path = (r.section_path or "").strip()
    for i, e in enumerate(expected):
        if r.document == e.document and (path == e.section or path.endswith(f"> {e.section}")):
            return i
    return None


@dataclass
class QuestionScores:
    recall_at_5: float
    recall_at_10: float
    precision_at_5: float
    reciprocal_rank: float
    ndcg_at_5: float
    ndcg_at_10: float
    hit_at_5: bool
    first_relevant_rank: int | None


def score(ranked: list[Retrieved], expected: list[Expected]) -> QuestionScores:
    assert expected, "score() is only defined for answerable questions"
    matches = [match(r, expected) for r in ranked]

    def recall(k: int) -> float:
        return len({m for m in matches[:k] if m is not None}) / len(expected)

    def ndcg(k: int) -> float:
        seen: set[int] = set()
        dcg = 0.0
        for i, m in enumerate(matches[:k], start=1):
            if m is not None and m not in seen:
                seen.add(m)
                dcg += 1 / math.log2(i + 1)
        ideal = sum(1 / math.log2(i + 1) for i in range(1, min(len(expected), k) + 1))
        return dcg / ideal

    first = next((i for i, m in enumerate(matches, start=1) if m is not None), None)
    return QuestionScores(
        recall_at_5=recall(5),
        recall_at_10=recall(10),
        precision_at_5=sum(m is not None for m in matches[:5]) / 5,
        reciprocal_rank=1 / first if first else 0.0,
        ndcg_at_5=ndcg(5),
        ndcg_at_10=ndcg(10),
        hit_at_5=first is not None and first <= 5,
        first_relevant_rank=first,
    )


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, math.ceil(p / 100 * len(ordered)) - 1))
    return ordered[k]


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
