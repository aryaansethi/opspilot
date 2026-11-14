"""Build a human spot-check sheet from the latest completed runs.

Picks 20 test questions (stratified by kind, fixed seed) and shows, for each: the expected
sections, the top 3 sections retrieved by the latest D_hybrid_rrf_rerank run, and the answer
from the latest answers run. A reviewer ticks whether the label and the answer are right.

Usage: uv run --project backend python evaluation/review_sample.py
"""

import asyncio
import random
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import dispose_engine, get_sessionmaker  # noqa: E402
from app.models import EvaluationResult, EvaluationRun  # noqa: E402

QUOTA = {"lexical": 5, "semantic": 8, "multi": 3, "unanswerable": 4}


async def latest(db, label: str) -> EvaluationRun | None:  # type: ignore[no-untyped-def]
    return await db.scalar(select(EvaluationRun).where(
        EvaluationRun.config_label == label, EvaluationRun.status == "completed", EvaluationRun.split == "test",
    ).order_by(EvaluationRun.finished_at.desc()).limit(1))


async def results(db, run: EvaluationRun | None) -> dict[str, EvaluationResult]:  # type: ignore[no-untyped-def]
    if run is None:
        return {}
    rows = await db.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
    return {r.question_id: r for r in rows}


async def main() -> int:
    async with get_sessionmaker()() as db:
        d_run, a_run = await latest(db, "D_hybrid_rrf_rerank"), await latest(db, "answers_hybrid_rrf")
        d_res, a_res = await results(db, d_run), await results(db, a_run)
    await dispose_engine()
    if not d_res:
        print("No completed D_hybrid_rrf_rerank test run; run evaluation/run.py --split test first.")
        return 1
    by_kind = defaultdict(list)
    for r in sorted(d_res.values(), key=lambda r: r.question_id):
        by_kind[r.kind].append(r)
    rnd = random.Random(42)
    sample = [r for kind, n in QUOTA.items() for r in rnd.sample(by_kind[kind], min(n, len(by_kind[kind])))]
    sample.sort(key=lambda r: r.question_id)

    lines = ["# Evaluation spot-check (20 test questions)", "",
             f"Generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC from retrieval run `{d_run.id}`"
             + (f" and answers run `{a_run.id}`" if a_run else " (no answers run yet)") + ".", "",
             "For each question, tick the boxes that are true. Leave a note when something is wrong.", ""]
    for r in sample:
        d = r.detail
        expected = ", ".join(f"{x['document']} › {x['section']}" for x in d.get("relevant", [])) or "— (unanswerable)"
        top3 = "\n".join(f"   {i}. {x['document']} › {(x['section'] or '').split(' > ')[-1]}"
                         for i, x in enumerate(d.get("retrieved", [])[:3], 1))
        lines += [f"## {r.question_id} ({r.kind}): {r.question}", "", f"- Expected: {expected}",
                  f"- Retrieved top 3 (D):\n{top3}"]
        ans = a_res.get(r.question_id)
        if ans is not None:
            ad = ans.detail
            if "error" in ad:
                lines.append(f"- Answer: model error ({ad['error'][:120]})")
            else:
                verdict = "abstained" if ad.get("insufficient_evidence") else "answered"
                lines.append(f"- Answer ({verdict}): {ad.get('answer', '')[:500]}")
        lines += ["", "- [ ] Expected sections are the right ones (label is correct)",
                  "- [ ] Answer is correct and supported by its citations (or correctly abstains)",
                  "- Note: ", ""]
    out = ROOT / "reports" / f"review-{datetime.now(UTC):%Y%m%d}.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
