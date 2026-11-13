import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SearchFilters:
    source_types: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    environments: tuple[str, ...] = ()


@dataclass
class Candidate:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    source_type: str
    content: str
    section_path: str | None
    page_start: int | None
    page_end: int | None
    char_start: int
    char_end: int
    lexical_rank: int | None = None
    lexical_score: float | None = None
    vector_rank: int | None = None
    vector_distance: float | None = None
    rrf_score: float = 0.0
    rerank_score: float | None = None
    extra: dict[str, object] = field(default_factory=dict)
