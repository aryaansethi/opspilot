import math

from app.evaluations.metrics import Expected, Retrieved, mean, percentile, score

E = [Expected("runbook", "Rollback"), Expected("inc-1", "Root cause")]


def r(doc: str, path: str | None) -> Retrieved:
    return Retrieved(doc, path)


def test_perfect_and_partial_rankings() -> None:
    perfect = score([r("runbook", "Runbook > Rollback"), r("inc-1", "INC-1 > Root cause")], E)
    assert perfect.recall_at_5 == 1 and perfect.reciprocal_rank == 1 and perfect.ndcg_at_10 == 1
    assert perfect.precision_at_5 == 2 / 5

    ranked = [
        r("other", "X > Rollback"),
        r("runbook", "Runbook > Rollback"),
        r("runbook", "Runbook > Rollback"),
        r("x", None),
        r("y", "y"),
        r("inc-1", "INC-1 > Root cause"),
    ]
    s = score(ranked, E)
    assert s.first_relevant_rank == 2 and s.reciprocal_rank == 0.5
    assert s.recall_at_5 == 0.5 and s.recall_at_10 == 1.0  # second section only at rank 6
    assert s.precision_at_5 == 2 / 5  # duplicate chunk counts for precision
    ideal = 1 + 1 / math.log2(3)
    assert (
        abs(s.ndcg_at_10 - (1 / math.log2(3) + 1 / math.log2(7)) / ideal) < 1e-12
    )  # duplicate not re-credited
    assert s.hit_at_5


def test_section_matching_is_exact_on_heading() -> None:
    assert (
        score(
            [r("runbook", "Runbook > Rollback procedure")], [Expected("runbook", "Rollback")]
        ).recall_at_10
        == 0
    )
    assert score([r("runbook", "Runbook")], [Expected("runbook", "Runbook")]).recall_at_10 == 1
    assert score([], E).reciprocal_rank == 0


def test_percentile_and_mean() -> None:
    assert percentile([5, 1, 3, 2, 4], 50) == 3 and percentile([5, 1, 3, 2, 4], 95) == 5
    assert percentile([], 50) == 0 and mean([]) == 0 and mean([1, 2]) == 1.5
