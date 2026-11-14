import uuid

from app.rag.fusion.rrf import dedupe_overlapping, reciprocal_rank_fusion
from app.rag.types import Candidate

DOC = uuid.uuid4()


def cand(
    name: str, *, lex: int | None = None, vec: int | None = None, span=(0, 100), doc=DOC
) -> Candidate:
    return Candidate(
        chunk_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        document_id=doc,
        document_title=name,
        source_type="runbook",
        content=name,
        section_path=None,
        page_start=None,
        page_end=None,
        char_start=span[0],
        char_end=span[1],
        lexical_rank=lex,
        vector_rank=vec,
    )


def test_rrf_formula_and_order() -> None:
    a_l, b_l = cand("a", lex=1), cand("b", lex=2)
    b_v, c_v = cand("b", vec=1), cand("c", vec=2)
    fused = reciprocal_rank_fusion([a_l, b_l], [b_v, c_v], k=60)
    assert [c.document_title for c in fused] == ["b", "a", "c"]
    b = fused[0]
    assert abs(b.rrf_score - (1 / 62 + 1 / 61)) < 1e-12
    assert b.lexical_rank == 2 and b.vector_rank == 1
    assert abs(fused[1].rrf_score - 1 / 61) < 1e-12


def test_rrf_single_list_and_empty() -> None:
    assert reciprocal_rank_fusion([], []) == []
    only = reciprocal_rank_fusion([], [cand("x", vec=1)], k=10)
    assert only[0].rrf_score == 1 / 11 and only[0].lexical_rank is None


def test_dedupe_drops_mostly_overlapping_chunks_of_same_doc() -> None:
    other_doc = uuid.uuid4()
    first = cand("first", span=(0, 100))
    overlap = cand("overlap", span=(20, 110))  # 80/90 covered
    neighbour = cand("neighbour", span=(90, 200))  # 10/110 covered
    same_span_other_doc = cand("other", span=(0, 100), doc=other_doc)
    kept = dedupe_overlapping([first, overlap, neighbour, same_span_other_doc])
    assert [c.document_title for c in kept] == ["first", "neighbour", "other"]


def test_rrf_ties_do_not_depend_on_random_ids() -> None:
    """Same content, different chunk ids (e.g. two databases) → same order."""
    import random

    def build(seed: int) -> list[str]:
        rnd = random.Random(seed)
        lex = []
        for i, name in enumerate(["beta", "alpha", "gamma"], start=1):
            c = cand(name, lex=i)
            c.chunk_id = uuid.UUID(int=rnd.getrandbits(128))
            lex.append(c)
        vec = []
        for i, name in enumerate(["gamma", "alpha", "beta"], start=1):
            c = cand(name, vec=i)
            c.chunk_id = next(x.chunk_id for x in lex if x.document_title == name)
            vec.append(c)
        return [c.document_title for c in reciprocal_rank_fusion(lex, vec)]

    # alpha (2,2) ties with beta (1,3) and gamma (3,1) on RRF score in some orders; order must be stable
    assert build(1) == build(2) == build(3)
