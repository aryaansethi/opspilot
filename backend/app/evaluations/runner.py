"""Evaluation runner: retrieval configs A-D and grounded-answer checks over dataset v1.

The corpus is ingested into a dedicated, isolated evaluation workspace using the
same parse → chunk → embed code as production ingestion (S3/SQS are skipped).
Every run records the dataset hash, configuration and per-question results, so
numbers can be reproduced and are never typed in by hand.
"""

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.core.security import hash_password
from app.evaluations.metrics import Expected, Retrieved, match, mean, percentile, score
from app.models import (
    Document,
    DocumentChunk,
    EvaluationResult,
    EvaluationRun,
    User,
    Workspace,
    WorkspaceMember,
)
from app.rag.chunking.chunker import chunk_document
from app.rag.embeddings.provider import EmbeddingProvider
from app.rag.generation.grounded import generate_grounded_answer
from app.rag.generation.llm import LLMProvider
from app.rag.ingestion.parsers import parse
from app.rag.lexical.postgres_fts import NAME as LEXICAL_NAME
from app.rag.pipeline import Mode, hybrid_search
from app.rag.reranking.reranker import CrossEncoderReranker, Reranker

DATASET_NAME = "opspilot-synthetic"
_EVAL_USER_EMAIL = "evaluation@opspilot.local"
_CORPUS_LOCK_KEY = 0x0F5_C0_4B  # arbitrary constant: one advisory lock for the evaluation corpus
EVAL_WORKSPACE_SLUG = "opspilot-eval-v1"


@dataclass(frozen=True)
class RetrievalConfig:
    label: str
    mode: Mode
    rerank: bool


RETRIEVAL_CONFIGS = {
    "A_lexical": RetrievalConfig("A_lexical", "lexical", False),
    "B_vector": RetrievalConfig("B_vector", "vector", False),
    "C_hybrid_rrf": RetrievalConfig("C_hybrid_rrf", "hybrid", False),
    "D_hybrid_rrf_rerank": RetrievalConfig("D_hybrid_rrf_rerank", "hybrid", True),
}


@dataclass
class Dataset:
    version: str
    hash: str
    corpus: dict[str, bytes]
    questions: list[dict[str, Any]]


def load_dataset(path: str | None = None) -> Dataset:
    root = Path(path or get_settings().evaluation_dataset_dir)
    corpus = {p.stem: p.read_bytes() for p in sorted((root / "corpus").glob("*.md"))}
    questions = [
        json.loads(line)
        for line in (root / "questions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    h = hashlib.sha256()
    for name, data in corpus.items():
        h.update(name.encode() + b"\0" + data)
    h.update((root / "questions.jsonl").read_bytes())
    return Dataset(version=root.name, hash=h.hexdigest(), corpus=corpus, questions=questions)


def _source_type(name: str) -> str:
    if name.startswith("inc-"):
        return "incident_report"
    if "architecture" in name:
        return "architecture"
    return "runbook" if "runbook" in name else "other"


async def ensure_eval_workspace(
    db: AsyncSession, ds: Dataset, embedder: EmbeddingProvider
) -> uuid.UUID:
    """Create the isolated evaluation workspace and (re)index the corpus when it changed.

    Safe with several workers: everything happens in ONE transaction that first takes a
    Postgres advisory lock, so a second worker waits and then finds the corpus already indexed.
    """
    await db.commit()  # start a fresh transaction so the lock covers all reads below
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CORPUS_LOCK_KEY})
    ws = await db.scalar(select(Workspace).where(Workspace.slug == EVAL_WORKSPACE_SLUG))
    if ws is None:
        user = await db.scalar(select(User).where(User.email == _EVAL_USER_EMAIL))
        if user is None:
            user = User(
                email=_EVAL_USER_EMAIL,
                display_name="Evaluation",
                password_hash=hash_password(secrets.token_urlsafe(32)),
            )  # nobody can sign in as this user
            db.add(user)
        ws = Workspace(name="Evaluation (synthetic v1)", slug=EVAL_WORKSPACE_SLUG)
        db.add(ws)
        await db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
        await db.flush()
    existing: dict[str, Document] = {}
    for d in await db.scalars(
        select(Document).where(Document.workspace_id == ws.id).order_by(Document.created_at)
    ):
        if d.filename in existing:  # self-heal duplicates left by an earlier concurrent run
            await db.delete(d)
        else:
            existing[d.filename] = d
    changed = 0
    for name, data in ds.corpus.items():
        filename = f"{name}.md"
        digest = hashlib.sha256(data).hexdigest()
        doc = existing.pop(filename, None)
        if (
            doc
            and doc.content_hash == digest
            and doc.embedding_model == embedder.model
            and doc.chunk_count
        ):
            continue
        if doc is None:
            doc = Document(
                workspace_id=ws.id,
                title=name,
                filename=filename,
                source_type=_source_type(name),
                s3_key=f"eval://{ds.version}/{filename}",
                mime_type="text/markdown",
                size_bytes=len(data),
            )
            db.add(doc)
            await db.flush()
        s = get_settings()
        chunks = chunk_document(
            parse(data, "text/markdown"), s.chunk_target_tokens, s.chunk_overlap_tokens
        )
        vectors = await embedder.embed([c.content for c in chunks])
        await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        db.add_all(
            DocumentChunk(
                workspace_id=ws.id,
                document_id=doc.id,
                chunk_index=c.index,
                content=c.content,
                section_path=c.section_path,
                page_start=c.page_start,
                page_end=c.page_end,
                char_start=c.char_start,
                char_end=c.char_end,
                token_estimate=c.token_estimate,
                content_hash=c.content_hash,
                embedding=v,
                embedding_model=embedder.model,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        doc.status, doc.content_hash, doc.chunk_count = "indexed", digest, len(chunks)
        doc.embedding_model, doc.indexed_at = embedder.model, datetime.now(UTC)
        changed += 1
    for stale in existing.values():  # documents removed from the dataset
        await db.delete(stale)
    await db.commit()
    log.info("evaluation.corpus_ready", documents=len(ds.corpus), reindexed=changed)
    return ws.id


def _questions(ds: Dataset, split: str) -> list[dict[str, Any]]:
    return [q for q in ds.questions if split == "all" or q["split"] == split]


async def _start_run(
    db: AsyncSession,
    ds: Dataset,
    kind: str,
    label: str,
    config: dict[str, Any],
    split: str,
    requested_by: uuid.UUID | None,
    run_id: uuid.UUID | None = None,
) -> EvaluationRun:
    """Create the run row, or fill in the one the API created when it queued the job."""
    run = await db.get(EvaluationRun, run_id) if run_id else None
    if run is None:
        run = EvaluationRun(
            id=run_id or uuid.uuid4(),
            dataset_name=DATASET_NAME,
            dataset_version=ds.version,
            kind=kind,
            config_label=label,
            split=split,
            requested_by=requested_by,
        )
        db.add(run)
    run.dataset_hash, run.config, run.status = ds.hash, config, "running"
    run.started_at = datetime.now(UTC)
    await db.commit()
    return run


async def _mark_failed(db: AsyncSession, run_id: uuid.UUID, exc: BaseException) -> EvaluationRun:
    """Record a failure. Uses the id captured before the error: rollback expires ORM objects."""
    await db.rollback()
    run = await db.get(EvaluationRun, run_id)
    assert run is not None
    run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
    log.error("evaluation.failed", run_id=str(run_id), error=repr(exc), exc_info=exc)
    return run


async def mark_run_failed(run_id: uuid.UUID, exc: BaseException) -> None:
    """Worker fallback when a run fails before or outside the runner's own error handling."""
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as db:
        run = await db.get(EvaluationRun, run_id)
        if run is not None and run.status == "running":
            run.status, run.error = "failed", f"{type(exc).__name__}: {exc}"[:2000]
            run.finished_at = datetime.now(UTC)
            await db.commit()


def _ranked(results: list[Any], doc_names: dict[uuid.UUID, str]) -> list[Retrieved]:
    return [Retrieved(doc_names[c.document_id], c.section_path) for c in results]


async def run_retrieval(
    db: AsyncSession,
    cfg: RetrievalConfig,
    *,
    embedder: EmbeddingProvider,
    split: str = "test",
    requested_by: uuid.UUID | None = None,
    reranker: Reranker | None = None,
    dataset: Dataset | None = None,
    run_id: uuid.UUID | None = None,
) -> EvaluationRun:
    ds = dataset or load_dataset()
    s = get_settings()
    ws_id = await ensure_eval_workspace(db, ds, embedder)
    rr = (
        reranker
        if reranker is not None
        else (CrossEncoderReranker(s.rerank_model) if cfg.rerank else None)
    )
    config = {
        "mode": cfg.mode,
        "rerank": cfg.rerank,
        "lexical": LEXICAL_NAME,
        "embedding_model": embedder.model,
        "reranker": rr.name if rr else None,
        "rrf_k": s.rrf_k,
        "candidates": s.retrieval_candidates,
        "rerank_candidates": s.rerank_candidates if rr else None,
        "top_k": 10,
        "chunk_target_tokens": s.chunk_target_tokens,
        "chunk_overlap_tokens": s.chunk_overlap_tokens,
    }
    run = await _start_run(db, ds, "retrieval", cfg.label, config, split, requested_by, run_id)
    current_run_id = run.id
    doc_names = {
        d.id: d.filename.removesuffix(".md")
        for d in await db.scalars(select(Document).where(Document.workspace_id == ws_id))
    }
    try:
        if rr is not None:  # load the model once so the first question's latency is not inflated
            await hybrid_search(
                db, ws_id, "warm up", embedder=embedder, reranker=rr, mode="hybrid", top_k=1
            )
        scores, latencies = [], []
        for q in _questions(ds, split):
            t = time.perf_counter()
            out = await hybrid_search(
                db, ws_id, q["question"], embedder=embedder, reranker=rr, mode=cfg.mode, top_k=10
            )
            latency = (time.perf_counter() - t) * 1000
            latencies.append(latency)
            ranked = _ranked(out.results, doc_names)
            detail: dict[str, Any] = {
                "retrieved": [{"document": x.document, "section": x.section_path} for x in ranked],
                "relevant": q["relevant"],
                "split": q["split"],
            }
            if q["answerable"]:
                sc = score(ranked, [Expected(r["document"], r["section"]) for r in q["relevant"]])
                scores.append((q, sc))
                detail.update(
                    recall_at_5=sc.recall_at_5,
                    recall_at_10=sc.recall_at_10,
                    ndcg_at_10=sc.ndcg_at_10,
                    precision_at_5=sc.precision_at_5,
                    first_relevant_rank=sc.first_relevant_rank,
                )
                db.add(
                    EvaluationResult(
                        run_id=run.id,
                        question_id=q["id"],
                        question=q["question"],
                        kind=q["kind"],
                        answerable=True,
                        hit_at_5=sc.hit_at_5,
                        reciprocal_rank=sc.reciprocal_rank,
                        latency_ms=latency,
                        detail=detail,
                    )
                )
            else:
                db.add(
                    EvaluationResult(
                        run_id=run.id,
                        question_id=q["id"],
                        question=q["question"],
                        kind=q["kind"],
                        answerable=False,
                        latency_ms=latency,
                        detail=detail,
                    )
                )

        def agg(attr: str, kind: str | None = None) -> float:
            return round(
                mean([getattr(sc, attr) for q, sc in scores if kind is None or q["kind"] == kind]),
                4,
            )

        run.metrics = {
            "recall_at_5": agg("recall_at_5"),
            "recall_at_10": agg("recall_at_10"),
            "precision_at_5": agg("precision_at_5"),
            "mrr": agg("reciprocal_rank"),
            "ndcg_at_5": agg("ndcg_at_5"),
            "ndcg_at_10": agg("ndcg_at_10"),
            "latency_p50_ms": round(percentile(latencies, 50), 1),
            "latency_p95_ms": round(percentile(latencies, 95), 1),
            "questions": len(latencies),
            "answerable_questions": len(scores),
            "by_kind": {
                k: {
                    "n": sum(1 for q, _ in scores if q["kind"] == k),
                    "recall_at_5": agg("recall_at_5", k),
                    "mrr": agg("reciprocal_rank", k),
                }
                for k in ("lexical", "semantic", "multi")
            },
        }
        run.status = "completed"
    except Exception as e:
        run = await _mark_failed(db, current_run_id, e)
    run.finished_at = datetime.now(UTC)
    await db.commit()
    return run


async def run_answers(
    db: AsyncSession,
    *,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    split: str = "test",
    requested_by: uuid.UUID | None = None,
    limit: int | None = None,
    dataset: Dataset | None = None,
    run_id: uuid.UUID | None = None,
) -> EvaluationRun:
    """Grounded-answer checks: abstention, citation precision/coverage, expected-fact match."""
    ds = dataset or load_dataset()
    s = get_settings()
    ws_id = await ensure_eval_workspace(db, ds, embedder)
    config = {
        "retrieval": "hybrid_rrf",
        "llm_model": llm.model,
        "embedding_model": embedder.model,
        "context_chunks": s.answer_context_chunks,
        "limit": limit,
        "faithfulness": "not measured (no LLM judge yet); see expected_fact_match",
    }
    run = await _start_run(
        db, ds, "answers", "answers_hybrid_rrf", config, split, requested_by, run_id
    )
    current_run_id = run.id
    doc_names = {
        d.id: d.filename.removesuffix(".md")
        for d in await db.scalars(select(Document).where(Document.workspace_id == ws_id))
    }
    qs = _questions(ds, split)[: limit or None]
    try:
        abstain_ok, cite_prec, cite_cov, fact_match, latencies, errors = [], [], [], [], [], 0
        unans: list[float] = []
        for q in qs:
            t = time.perf_counter()
            out = await hybrid_search(
                db, ws_id, q["question"], embedder=embedder, top_k=s.answer_context_chunks
            )
            try:
                g = await generate_grounded_answer(llm, q["question"], out.results)
            except Exception as e:  # noqa: BLE001 - count model failures instead of aborting the run
                errors += 1
                db.add(
                    EvaluationResult(
                        run_id=run.id,
                        question_id=q["id"],
                        question=q["question"],
                        kind=q["kind"],
                        answerable=q["answerable"],
                        latency_ms=(time.perf_counter() - t) * 1000,
                        detail={"error": f"{type(e).__name__}: {e}"[:500]},
                    )
                )
                continue
            latency = (time.perf_counter() - t) * 1000
            latencies.append(latency)
            correct_abstention = g.insufficient_evidence != q["answerable"]
            abstain_ok.append(1.0 if correct_abstention else 0.0)
            if not q["answerable"]:
                unans.append(1.0 if correct_abstention else 0.0)
            detail: dict[str, Any] = {
                "answer": g.answer,
                "insufficient_evidence": g.insufficient_evidence,
                "citations": [
                    {"document": doc_names[c.document_id], "section": c.section_path}
                    for c in g.citations
                ],
                "removed_labels": g.removed_labels,
                "correct_abstention": correct_abstention,
            }
            rr = 0.0
            if q["answerable"] and not g.insufficient_evidence:
                expected = [Expected(r["document"], r["section"]) for r in q["relevant"]]
                cited = _ranked(g.citations, doc_names)

                hits = [match(c, expected) is not None for c in cited]
                if cited:
                    cite_prec.append(sum(hits) / len(hits))
                cite_cov.append(1.0 if any(hits) else 0.0)
                facts = q.get("expected_facts") or []
                if facts:
                    fact_match.append(
                        1.0 if all(f.lower() in g.answer.lower() for f in facts) else 0.0
                    )
                rr = 1.0 if any(hits) else 0.0
                detail.update(citation_hits=hits)
            db.add(
                EvaluationResult(
                    run_id=run.id,
                    question_id=q["id"],
                    question=q["question"],
                    kind=q["kind"],
                    answerable=q["answerable"],
                    hit_at_5=rr == 1.0,
                    reciprocal_rank=rr,
                    latency_ms=latency,
                    detail=detail,
                )
            )
            await db.commit()
            log.info(
                "evaluation.answer",
                question=q["id"],
                abstained=g.insufficient_evidence,
                ok=correct_abstention,
            )
        run.metrics = {
            "abstention_accuracy": round(mean(abstain_ok), 4),
            "unanswerable_abstention_rate": round(mean(unans), 4) if unans else None,
            "citation_precision": round(mean(cite_prec), 4),
            "citation_coverage": round(mean(cite_cov), 4),
            "expected_fact_match": round(mean(fact_match), 4),
            "latency_p50_ms": round(percentile(latencies, 50), 1),
            "latency_p95_ms": round(percentile(latencies, 95), 1),
            "questions": len(qs),
            "model_errors": errors,
        }
        run.status = "completed"
    except Exception as e:
        run = await _mark_failed(db, current_run_id, e)
    run.finished_at = datetime.now(UTC)
    await db.commit()
    return run
