"""Embedding providers.

`OpenAICompatibleEmbeddings` talks to any OpenAI-compatible /v1/embeddings API:
Ollama locally (default, free) or OpenAI by changing LLM_BASE_URL / LLM_API_KEY.
"""

import hashlib
import math
from typing import Protocol

from openai import AsyncOpenAI

from app.core.config import Settings, get_settings


class EmbeddingProvider(Protocol):
    model: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingError(RuntimeError):
    pass


class OpenAICompatibleEmbeddings:
    def __init__(self, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        self.model = s.embedding_model
        self.dim = s.embedding_dim
        self._batch = s.embedding_batch_size
        self._client = AsyncOpenAI(
            base_url=s.llm_base_url,
            api_key=s.llm_api_key.get_secret_value(),
            timeout=s.llm_timeout_seconds,
            max_retries=2,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self._batch):
            batch = texts[i : i + self._batch]
            resp = await self._client.embeddings.create(model=self.model, input=batch)
            vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
            for v in vectors:
                if len(v) != self.dim:
                    raise EmbeddingError(
                        f"{self.model} returned {len(v)} dims, expected {self.dim} "
                        "(EMBEDDING_DIM must match the model and the DB column)"
                    )
            out.extend(vectors)
        return out


class HashingEmbeddings:
    """Deterministic bag-of-words vectors for tests only. Not semantically meaningful."""

    def __init__(self, dim: int = 1024) -> None:
        self.model = "test-hashing"
        self.dim = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            v = [0.0] * self.dim
            for word in text.lower().split():
                h = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16)
                v[h % self.dim] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            vectors.append([x / norm for x in v])
        return vectors


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = OpenAICompatibleEmbeddings()
    return _provider


def set_embedding_provider(provider: EmbeddingProvider | None) -> None:
    """Test hook."""
    global _provider
    _provider = provider
