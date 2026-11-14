"""Run OpsPilot evaluations and write a Markdown + JSON report.

Usage (from the repo root; needs docker compose services and Ollama):
  uv run --project backend python evaluation/run.py                      # retrieval A-D on the test split
  uv run --project backend python evaluation/run.py --split tune         # tuning split
  uv run --project backend python evaluation/run.py --answers --limit 30 # grounded-answer checks (slow: LLM)

Every number in the report comes from this run; nothing is entered by hand.
"""

import argparse
import asyncio
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.core.config import get_settings  # noqa: E402
from app.db.session import dispose_engine, get_sessionmaker  # noqa: E402
from app.evaluations.runner import RETRIEVAL_CONFIGS, run_answers, run_retrieval  # noqa: E402
from app.rag.embeddings.provider import get_embedding_provider  # noqa: E402
from app.rag.generation.llm import get_llm  # noqa: E402

COLS = [("recall_at_5", "Recall@5"), ("recall_at_10", "Recall@10"), ("precision_at_5", "P@5"), ("mrr", "MRR"),
        ("ndcg_at_5", "nDCG@5"), ("ndcg_at_10", "nDCG@10"), ("latency_p50_ms", "p50 ms"), ("latency_p95_ms", "p95 ms")]


RETRIEVAL_NOTES = [
    "Relevance is binary at section level; unanswerable questions are excluded from retrieval metrics.",
    "Lexical retrieval is PostgreSQL full-text search (`ts_rank_cd`), not BM25.",
    "Latency is measured in-process on this machine and includes query embedding (and reranking for D).",
    "Synthetic corpus; small sample. These numbers do not predict production performance.",
]
ANSWER_NOTES = [
    "Retrieval is hybrid RRF (config C); answers come from the local LLM with citation validation.",
    "abstention_accuracy: answers answerable questions and abstains on unanswerable ones.",
    "citation_precision / citation_coverage: cited chunks that are in an expected section / answers with at least one such citation (answered, answerable questions only).",
    "expected_fact_match: every expected key phrase appears verbatim in the answer; it under-counts correct paraphrases.",
    "Faithfulness is not measured (no LLM judge or full human grading yet).",
    "Latency includes retrieval and local LLM generation on one laptop.",
    "Synthetic corpus; small sample. These numbers do not predict production performance.",
]


def fmt(v: object) -> str:
    return f"{v:.3f}" if isinstance(v, float) and v <= 1 else str(v)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="test", choices=["test", "tune", "all"])
    ap.add_argument("--configs", default="all", help="comma list of A_lexical,B_vector,C_hybrid_rrf,D_hybrid_rrf_rerank")
    ap.add_argument("--answers", action="store_true", help="run grounded-answer checks instead of retrieval")
    ap.add_argument("--limit", type=int, default=None, help="answers: only the first N questions")
    args = ap.parse_args()
    s = get_settings()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    env = {"python": platform.python_version(), "machine": platform.machine(), "system": platform.system(),
           "embedding_model": s.embedding_model, "llm_model": s.llm_model, "generated_at": datetime.now(UTC).isoformat()}
    runs = []
    async with get_sessionmaker()() as db:
        if args.answers:
            runs.append(await run_answers(db, embedder=get_embedding_provider(), llm=get_llm(), split=args.split, limit=args.limit))
        else:
            labels = list(RETRIEVAL_CONFIGS) if args.configs == "all" else args.configs.split(",")
            for label in labels:
                print(f"running {label} ...", flush=True)
                runs.append(await run_retrieval(db, RETRIEVAL_CONFIGS[label], embedder=get_embedding_provider(), split=args.split))
    await dispose_engine()

    for r in runs:
        if r.status != "completed":
            print(f"{r.config_label}: {r.status} {r.error}")
    first = runs[0]
    kind = "answers" if args.answers else "retrieval"
    lines = [f"# OpsPilot {kind} evaluation — {first.dataset_name} {first.dataset_version} ({args.split} split)", "",
             f"- Generated: {env['generated_at']}", f"- Dataset hash: `{first.dataset_hash[:16]}`",
             f"- Environment: {env['system']} {env['machine']}, Python {env['python']}",
             f"- Embedding model: `{env['embedding_model']}`" + (f", LLM: `{env['llm_model']}`" if args.answers else ""),
             f"- Questions: {first.metrics.get('questions') if first.metrics else '?'}", ""]
    if args.answers:
        m = first.metrics or {}
        lines += ["| Metric | Value |", "|---|---|"] + [f"| {k} | {fmt(v)} |" for k, v in m.items()]
    else:
        lines += ["| Config | " + " | ".join(c for _, c in COLS) + " |", "|---" * (len(COLS) + 1) + "|"]
        for r in runs:
            m = r.metrics or {}
            lines.append(f"| {r.config_label} | " + " | ".join(fmt(m.get(k, "—")) for k, _ in COLS) + " |")
        lines += ["", "Recall@5 by question kind:", "", "| Config | lexical | semantic | multi |", "|---|---|---|---|"]
        for r in runs:
            bk = (r.metrics or {}).get("by_kind", {})
            lines.append(f"| {r.config_label} | " + " | ".join(
                f"{fmt(bk.get(k, {}).get('recall_at_5', 0.0))} (n={bk.get(k, {}).get('n', 0)})" for k in ("lexical", "semantic", "multi")) + " |")
    if args.answers:
        lines += ["", "Notes:", *[f"- {n}" for n in ANSWER_NOTES]]
    else:
        lines += ["", "Notes:", *[f"- {n}" for n in RETRIEVAL_NOTES]]
    md = "\n".join(lines) + "\n"
    out = ROOT / "reports" / f"{stamp}-{kind}-{args.split}"
    out.with_suffix(".md").write_text(md)
    out.with_suffix(".json").write_text(json.dumps({"environment": env, "runs": [
        {"id": str(r.id), "config_label": r.config_label, "config": r.config, "status": r.status, "metrics": r.metrics,
         "dataset_hash": r.dataset_hash, "split": r.split} for r in runs]}, indent=2))
    print(md)
    print(f"wrote {out.with_suffix('.md')}")
    return 0 if all(r.status == "completed" for r in runs) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
