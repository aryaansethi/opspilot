"""Why does equal-weight RRF trail vector-only? Offline diagnosis + tuning on the TUNE split only.

For each tune question this fetches the lexical and vector candidate lists once (the real
production queries), then replays fusion variants in Python and scores them with the
evaluation metrics. Nothing here touches the test split.

Usage: uv run --project backend python evaluation/experiments/fusion_sweep.py [--dataset v2]
Writes evaluation/experiments/fusion_sweep-<dataset>.md
"""

import argparse
import asyncio
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db.session import dispose_engine, get_sessionmaker  # noqa: E402
from app.evaluations.metrics import Expected, Retrieved, mean, score  # noqa: E402
from app.evaluations.runner import ensure_eval_workspace, load_dataset  # noqa: E402
from app.models import Document  # noqa: E402
from app.rag.embeddings.provider import get_embedding_provider  # noqa: E402
from app.rag.fusion.rrf import dedupe_overlapping, weighted_rrf  # noqa: E402
from app.rag.lexical.postgres_fts import lexical_search  # noqa: E402
from app.rag.types import SearchFilters  # noqa: E402
from app.rag.vector.pgvector_search import vector_search  # noqa: E402


async def collect(version: str) -> tuple[list[dict], dict]:
    ds = load_dataset(version)
    emb = get_embedding_provider()
    out = []
    async with get_sessionmaker()() as db:
        ws = await ensure_eval_workspace(db, ds, emb)
        names = {d.id: d.filename.removesuffix(".md")
                 for d in await db.scalars(select(Document).where(Document.workspace_id == ws))}
        for q in ds.questions:
            if q["split"] != "tune" or not q["answerable"]:
                continue
            lex_or = await lexical_search(db, ws, q["question"], SearchFilters(), 50)
            lex_and = await lexical_search(db, ws, q["question"], SearchFilters(), 50, match_all=True)
            [v] = await emb.embed([q["question"]])
            vec = await vector_search(db, ws, v, SearchFilters(), 50, emb.model)
            out.append({"q": q, "lex_or": lex_or, "lex_and": lex_and, "vec": vec})
    await dispose_engine()
    return out, names


def evaluate(rows: list[dict], names: dict, fuse) -> dict[str, float]:  # type: ignore[no-untyped-def]
    scores = []
    for r in rows:
        ranked = fuse(r)[:10]
        exp = [Expected(x["document"], x["section"]) for x in r["q"]["relevant"]]
        scores.append(score([Retrieved(names[c.document_id], c.section_path) for c in ranked], exp, r["q"].get("match", "all")))
    return {"recall_at_5": mean([s.recall_at_5 for s in scores]), "mrr": mean([s.reciprocal_rank for s in scores]),
            "ndcg_at_10": mean([s.ndcg_at_10 for s in scores])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="v2")
    args = ap.parse_args()
    rows, names = asyncio.run(collect(args.dataset))

    # --- diagnosis: where is the first relevant chunk in each list?
    def first_rank(cands: list, q: dict) -> int | None:
        exp = [Expected(x["document"], x["section"]) for x in q["relevant"]]
        from app.evaluations.metrics import match
        return next((i for i, c in enumerate(cands, 1) if match(Retrieved(names[c.document_id], c.section_path), exp) is not None), None)

    lex_better = vec_better = same = lex_miss = 0
    lex_top1_wrong_vec_right = 0
    for r in rows:
        lr, vr = first_rank(r["lex_or"], r["q"]), first_rank(r["vec"], r["q"])
        if lr is None:
            lex_miss += 1
        if lr and vr:
            lex_better += lr < vr
            vec_better += vr < lr
            same += lr == vr
        if vr == 1 and (lr is None or lr > 1):
            lex_top1_wrong_vec_right += 1
    avg_lex_hits = mean([len(r["lex_or"]) for r in rows])

    variants = {}

    def add(name: str, fuse) -> None:  # type: ignore[no-untyped-def]
        variants[name] = evaluate(rows, names, fuse)

    add("vector only (B)", lambda r: dedupe_overlapping(copy.deepcopy(r["vec"])))
    add("lexical OR only (A)", lambda r: dedupe_overlapping(copy.deepcopy(r["lex_or"])))
    add("lexical AND-first only", lambda r: dedupe_overlapping(copy.deepcopy(r["lex_and"] or r["lex_or"])))
    for lex_key in ("lex_or", "lex_and"):
        for w in (1.0, 0.75, 0.5, 0.35, 0.25):
            for depth in (50, 20, 10):
                def fuse(r, lex_key=lex_key, w=w, depth=depth):  # type: ignore[no-untyped-def]
                    lex = r[lex_key] or r["lex_or"]
                    return dedupe_overlapping(weighted_rrf(copy.deepcopy(lex[:depth]), copy.deepcopy(r["vec"]),
                                                           k=60, lexical_weight=w, vector_weight=1.0))
                add(f"RRF k=60 lexical={'AND-first' if lex_key == 'lex_and' else 'OR'} w_lex={w} depth={depth}", fuse)

    best = max((k for k in variants if k.startswith("RRF")), key=lambda k: (variants[k]["mrr"], variants[k]["ndcg_at_10"]))
    lines = [f"# Fusion sweep on dataset {args.dataset}, TUNE split ({len(rows)} answerable questions)", "",
             "## Diagnosis", "",
             f"- Lexical (OR) returns {avg_lex_hits:.1f} of 50 possible candidates per question on average: almost every "
             "chunk shares some word with a natural-language question, so the lexical list is long and noisy.",
             f"- First relevant chunk: lexical ranks it higher in {lex_better} questions, vector in {vec_better}, tie in {same}; "
             f"lexical misses it entirely in {lex_miss}.",
             f"- In {lex_top1_wrong_vec_right} questions vector has the right chunk at rank 1 but lexical does not. Equal-weight "
             "RRF gives both lists the same vote, so a confident vector rank 1 can be pushed down by lexical noise.", "",
             "## Variants (k = 60 throughout; vector weight 1.0)", "",
             "| Variant | Recall@5 | MRR | nDCG@10 |", "|---|---|---|---|"]
    for name, m in sorted(variants.items(), key=lambda kv: -kv[1]["mrr"]):
        mark = " **(selected)**" if name == best else ""
        lines.append(f"| {name}{mark} | {m['recall_at_5']:.3f} | {m['mrr']:.3f} | {m['ndcg_at_10']:.3f} |")
    lines += ["", f"Selected by highest MRR (then nDCG@10) among fusion variants: **{best}**.",
              "This selection uses only the tune split; the test split is evaluated afterwards as config E."]
    out = Path(__file__).with_name(f"fusion_sweep-{args.dataset}.md")
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))
    print(f"... {len(variants)} variants; best: {best} {variants[best]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
