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
