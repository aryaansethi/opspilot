"""Evaluation runner + API on the real v1 dataset, with deterministic fake embeddings and LLM."""

import json
import uuid
from typing import Any

from httpx import AsyncClient

from app.db.session import get_sessionmaker
from app.documents import storage
from app.evaluations.runner import RETRIEVAL_CONFIGS, load_dataset, run_answers, run_retrieval
from app.rag.embeddings.provider import HashingEmbeddings
from tests.conftest import register
from tests.test_documents import ws_headers

API = "/api/v1"


def test_dataset_is_consistent() -> None:
    ds = load_dataset()
    assert len(ds.questions) == 100 and len(ds.corpus) == 24 and len(ds.hash) == 64
    assert sum(q["split"] == "test" for q in ds.questions) == 70
    for q in ds.questions:
        assert q["answerable"] == bool(q["relevant"])
        for r in q["relevant"]:
            assert r["document"] in ds.corpus


async def test_retrieval_run_records_metrics_and_results() -> None:
    async with get_sessionmaker()() as db:
        run = await run_retrieval(
            db, RETRIEVAL_CONFIGS["A_lexical"], embedder=HashingEmbeddings(), split="test"
        )
        assert run.status == "completed", run.error
        m = run.metrics or {}
        assert m["questions"] == 70 and m["answerable_questions"] == 56
        assert (
            0 < m["recall_at_5"] <= 1
            and 0 < m["mrr"] <= 1
            and m["latency_p95_ms"] >= m["latency_p50_ms"]
        )
        assert (
            run.config["lexical"] == "postgres_fts_ts_rank_cd" and run.config["mode"] == "lexical"
        )
        # second run reuses the indexed corpus (same hash) and is reproducible
        again = await run_retrieval(
            db, RETRIEVAL_CONFIGS["A_lexical"], embedder=HashingEmbeddings(), split="test"
        )
        assert again.dataset_hash == run.dataset_hash
        assert {k: v for k, v in (again.metrics or {}).items() if "latency" not in k} == {
            k: v for k, v in m.items() if "latency" not in k
        }


class AbstainingLLM:
    model = "fake"

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        if "ERR_POOL_TIMEOUT" in user and "ERR_POOL_TIMEOUT" in user.split("Evidence:")[0]:
            return {
                "answer": "The HikariCP pool is exhausted [E1].",
                "claims": [{"text": "pool exhausted", "evidence": ["E1"]}],
                "insufficient_evidence": False,
            }
        return {"answer": "", "claims": [], "insufficient_evidence": True}


async def test_answer_run_measures_abstention_and_citations() -> None:
    async with get_sessionmaker()() as db:
        run = await run_answers(db, embedder=HashingEmbeddings(), llm=AbstainingLLM(), split="all")
    assert run.status == "completed", run.error
    m = run.metrics or {}
    assert m["questions"] == 100 and m["model_errors"] == 0
    assert m["unanswerable_abstention_rate"] == 1.0  # always abstains → every unanswerable is right
    assert 0.2 <= m["abstention_accuracy"] < 0.3  # ...and nearly every answerable is wrong
    assert m["citation_coverage"] in (0.0, 1.0)  # the one answered question was scored


async def test_api_queues_and_reports_runs(client: AsyncClient) -> None:
    u = await register(client)
    h = ws_headers(u)
    bad = await client.post(f"{API}/evaluations/run", headers=h, json={"config_label": "Z"})
    assert bad.status_code == 400
    r = await client.post(f"{API}/evaluations/run", headers=h, json={"config_label": "B_vector"})
    assert r.status_code == 202 and r.json()["status"] == "running"
    run_id = r.json()["id"]
    msgs = await storage.receive("opspilot-evaluate-test", wait_seconds=1)
    body = json.loads(msgs[0]["Body"])
    assert body["run_id"] == run_id and body["config_label"] == "B_vector"
    await storage.ack("opspilot-evaluate-test", msgs[0]["ReceiptHandle"])
    async with get_sessionmaker()() as db:  # what the worker does with the message
        await run_retrieval(
            db,
            RETRIEVAL_CONFIGS["B_vector"],
            embedder=HashingEmbeddings(),
            run_id=uuid.UUID(run_id),
        )
    runs = (await client.get(f"{API}/evaluations/runs", headers=h)).json()
    assert (
        runs[0]["id"] == run_id
        and runs[0]["status"] == "completed"
        and runs[0]["metrics"]["questions"] == 70
    )
    detail = (await client.get(f"{API}/evaluations/runs/{run_id}", headers=h)).json()
    assert len(detail["results"]) == 70 and {"hit_at_5", "reciprocal_rank", "latency_ms"} <= set(
        detail["results"][0]
    )
    all_four = await client.post(f"{API}/evaluations/run", headers=h, json={})
    assert all_four.status_code == 202
    assert (
        len(await storage.receive("opspilot-evaluate-test", wait_seconds=1, max_messages=10)) == 4
    )


async def test_concurrent_workers_index_the_corpus_once() -> None:
    """Two workers starting evaluations at the same time must not duplicate the corpus."""
    import asyncio

    from sqlalchemy import func, select

    from app.evaluations.runner import ensure_eval_workspace
    from app.models import Document

    ds = load_dataset()

    async def one() -> uuid.UUID:
        async with get_sessionmaker()() as db:
            return await ensure_eval_workspace(db, ds, HashingEmbeddings())

    a, b = await asyncio.gather(one(), one())
    assert a == b
    async with get_sessionmaker()() as db:
        n = await db.scalar(
            select(func.count()).select_from(Document).where(Document.workspace_id == a)
        )
    assert n == 24


async def test_duplicate_corpus_documents_are_removed() -> None:
    from sqlalchemy import func, select

    from app.evaluations.runner import ensure_eval_workspace
    from app.models import Document

    ds = load_dataset()
    async with get_sessionmaker()() as db:
        ws = await ensure_eval_workspace(db, ds, HashingEmbeddings())
        first = await db.scalar(select(Document).where(Document.workspace_id == ws).limit(1))
        assert first is not None
        db.add(
            Document(
                workspace_id=ws,
                title=first.title,
                filename=first.filename,
                source_type=first.source_type,
                s3_key="eval://dup",
                mime_type="text/markdown",
                size_bytes=1,
                status="indexed",
            )
        )
        await db.commit()
        await ensure_eval_workspace(db, ds, HashingEmbeddings())
        n = await db.scalar(
            select(func.count()).select_from(Document).where(Document.workspace_id == ws)
        )
    assert n == 24


class FailingEmbeddings(HashingEmbeddings):
    def __init__(self, fail_after: int) -> None:
        super().__init__()
        self.calls, self.fail_after = 0, fail_after

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls > self.fail_after:
            raise RuntimeError("embedding service unavailable")
        return await super().embed(texts)


async def test_failure_inside_a_run_marks_it_failed() -> None:
    async with get_sessionmaker()() as db:
        await run_retrieval(
            db, RETRIEVAL_CONFIGS["A_lexical"], embedder=HashingEmbeddings()
        )  # index corpus
        run = await run_retrieval(
            db, RETRIEVAL_CONFIGS["B_vector"], embedder=FailingEmbeddings(fail_after=0)
        )
    assert run.status == "failed" and "embedding service unavailable" in (run.error or "")
    assert run.finished_at is not None


async def test_worker_marks_run_failed_when_it_fails_before_starting(
    client: AsyncClient, monkeypatch: Any
) -> None:
    """Fails during corpus indexing (before the runner's own error handling): the worker records it."""
    from app import worker

    u = await register(client)
    r = await client.post(
        f"{API}/evaluations/run", headers=ws_headers(u), json={"config_label": "C_hybrid_rrf"}
    )
    run_id = r.json()["id"]
    monkeypatch.setattr(worker, "get_embedding_provider", lambda: FailingEmbeddings(fail_after=0))
    await worker.handle_evaluation(
        {"run_id": run_id, "config_label": "C_hybrid_rrf", "split": "test"}
    )  # must not raise
    detail = (await client.get(f"{API}/evaluations/runs/{run_id}", headers=ws_headers(u))).json()
    assert detail["status"] == "failed" and "embedding service unavailable" in detail["error"]


async def test_rerank_config_is_skipped_or_refused_when_not_installed(
    client: AsyncClient, monkeypatch: Any
) -> None:
    from app.evaluations import router as eval_router

    monkeypatch.setattr(eval_router, "rerank_available", lambda: False)
    url = storage.sqs().get_queue_url(QueueName="opspilot-evaluate-test")["QueueUrl"]
    storage.sqs().purge_queue(QueueUrl=url)  # messages left by earlier tests
    u = await register(client)
    h = ws_headers(u)
    caps = (await client.get(f"{API}/evaluations/capabilities", headers=h)).json()
    assert (
        "D_hybrid_rrf_rerank" in caps["unavailable"]
        and "D_hybrid_rrf_rerank" not in caps["available_configs"]
    )
    only_d = await client.post(
        f"{API}/evaluations/run", headers=h, json={"config_label": "D_hybrid_rrf_rerank"}
    )
    assert only_d.status_code == 400 and "INSTALL_RERANK" in only_d.json()["error"]["message"]
    assert (await client.post(f"{API}/evaluations/run", headers=h, json={})).status_code == 202
    labels = sorted(
        json.loads(m["Body"])["config_label"]
        for m in await storage.receive("opspilot-evaluate-test", wait_seconds=1, max_messages=10)
    )
    assert labels == ["A_lexical", "B_vector", "C_hybrid_rrf"]
