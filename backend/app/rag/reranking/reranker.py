"""Optional cross-encoder reranking over a bounded candidate set.

Requires the optional dependency group: `uv sync --group rerank`.
The model is downloaded once from Hugging Face and runs locally (free).
"""

import asyncio
from functools import lru_cache
from typing import Any, Protocol

from app.rag.types import Candidate


def rerank_available() -> bool:
    """True when the optional cross-encoder dependency group is installed."""
    import importlib.util

    return importlib.util.find_spec("sentence_transformers") is not None


class Reranker(Protocol):
    name: str

    async def rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]: ...


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        self.name = model_name

    @staticmethod
    @lru_cache(maxsize=2)
    def _model(name: str) -> Any:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Reranking needs `uv sync --group rerank`") from e
        return CrossEncoder(name, max_length=512)

    async def rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return candidates
        model = self._model(self.name)
        pairs = [(query, c.content) for c in candidates]
        scores = await asyncio.to_thread(model.predict, pairs)
        for c, s in zip(candidates, scores, strict=True):
            c.rerank_score = float(s)
        return sorted(candidates, key=lambda c: -(c.rerank_score or 0.0))


def default_reranker() -> "Reranker | None":
    """The product's reranking choice (settings.rerank_enabled; None = use it when installed)."""
    from app.core.config import get_settings

    s = get_settings()
    enabled = rerank_available() if s.rerank_enabled is None else s.rerank_enabled
    return _cached_reranker(s.rerank_model) if enabled else None


@lru_cache(maxsize=2)
def _cached_reranker(model: str) -> "CrossEncoderReranker":
    return CrossEncoderReranker(model)
