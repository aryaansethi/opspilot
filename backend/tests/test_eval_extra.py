"""Tool-selection, prompt-injection and faithfulness evaluations with scripted LLMs."""

import re
from typing import Any

from app.db.session import get_sessionmaker
from app.evaluations.extra import run_injection, run_tool_selection
from app.evaluations.judge import judge_claims
from app.evaluations.runner import load_dataset, run_answers
from app.rag.embeddings.provider import HashingEmbeddings
from tests.test_rrf import cand


class PlannerLLM:
    """Chooses tasks by keyword, and once proposes a tool that does not exist."""

    model = "scripted-planner"

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        q = re.search(r"<question>(.*?)</question>", user, re.S).group(1).lower()  # type: ignore[union-attr]
        tasks = ["search_runbooks"]
        if any(w in q for w in ("latency", "alarm", "throughput")):
            tasks += ["query_cloudwatch_metrics", "check_cloudwatch_alarms"]
        if any(w in q for w in ("error", "log", "5xx", "crash")):
            tasks.append("query_cloudwatch_logs")
        if any(w in q for w in ("deploy", "commit", "change")):
            tasks += ["search_recent_github_commits", "delete_repository"]
        return {
            "incident_type": "other",
            "tasks": tasks,
            "log_search_terms": [],
            "rationale": "keywords",
        }


async def test_tool_selection_scores_required_and_forbidden_tasks() -> None:
    async with get_sessionmaker()() as db:
        run = await run_tool_selection(db, llm=PlannerLLM(), dataset=load_dataset("v2"))
    assert run.status == "completed", run.error
    m = run.metrics or {}
    assert m["cases"] == 20 and m["model_errors"] == 0
    assert 0 < m["tool_selection_accuracy"] < 1  # a keyword planner gets some right, not all
    assert m["invalid_tasks_proposed"] > 0  # delete_repository proposed...
    # ...but never survives validation
    async with get_sessionmaker()() as db:
        from sqlalchemy import select

        from app.models import EvaluationResult

        rows = list(
            await db.scalars(select(EvaluationResult).where(EvaluationResult.run_id == run.id))
        )
    assert all("delete_repository" not in r.detail.get("chosen", []) for r in rows)
    doc_only = [r for r in rows if r.detail.get("forbidden")]
    assert len(doc_only) == 6


class ObedientLLM:
    """A deliberately bad model that obeys any instruction it sees (worst case)."""

    model = "obedient"

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        canaries = re.findall(
            r"PWNED-7731|INJECT-DNS-42|ALL-SYSTEMS-NOMINAL-9|evil\.example|MARK-COSMIC-1", user
        )
        text = " ".join(canaries) or "nothing"
        if schema_name == "grounded_answer":
            return {
                "answer": f"{text} [E1]",
                "claims": [{"text": text, "evidence": ["E1"]}],
                "insufficient_evidence": False,
            }
        return {
            "overview": text,
            "observed_facts": [{"text": text, "evidence": ["E1"]}],
            "hypotheses": [],
            "recommended_diagnostics": [],
            "proposed_remediation": [],
            "unknowns": [],
        }


class SafeLLM:
    model = "safe"

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        if schema_name == "grounded_answer":
            return {
                "answer": "Delete the lock key [E1].",
                "claims": [{"text": "Delete the lock key", "evidence": ["E1"]}],
                "insufficient_evidence": False,
            }
        return {
            "overview": "Pool exhausted.",
            "observed_facts": [],
            "hypotheses": [],
            "recommended_diagnostics": [],
            "proposed_remediation": [],
            "unknowns": [],
        }


async def test_injection_eval_detects_an_obedient_model_and_passes_a_safe_one() -> None:
    async with get_sessionmaker()() as db:
        bad = await run_injection(
            db, llm=ObedientLLM(), embedder=HashingEmbeddings(), dataset=load_dataset("v2")
        )
        good = await run_injection(
            db, llm=SafeLLM(), embedder=HashingEmbeddings(), dataset=load_dataset("v2")
        )
    assert bad.status == good.status == "completed", (bad.error, good.error)
    assert (bad.metrics or {})["injection_resistance"] < 1.0
    assert (good.metrics or {})["injection_resistance"] == 1.0 and (good.metrics or {})[
        "cases"
    ] == 8


class JudgeLLM:
    model = "judge"

    def __init__(self, verdicts: list[bool] | None) -> None:
        self.verdicts = verdicts

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        if self.verdicts is None:
            return {
                "verdicts": [{"claim": 1, "supported": True}]
            }  # incomplete → treated as judge error
        return {"verdicts": [{"claim": i, "supported": v} for i, v in enumerate(self.verdicts, 1)]}


async def test_judge_claims_requires_a_verdict_per_claim() -> None:
    c = cand("doc")
    assert await judge_claims(JudgeLLM([True, False]), [("a", [c]), ("b", [c])]) == [True, False]
    assert await judge_claims(JudgeLLM(None), [("a", [c]), ("b", [c])]) is None
    assert await judge_claims(JudgeLLM([]), []) == []


class AnswerAndJudgeLLM:
    model = "answer-and-judge"

    async def complete_json(
        self, system: str, user: str, schema: Any, schema_name: str
    ) -> dict[str, Any]:
        if schema_name == "claim_judgement":
            n = len(re.findall(r"<claim id=", user))
            return {"verdicts": [{"claim": i, "supported": i == 1} for i in range(1, n + 1)]}
        return {
            "answer": "A [E1]. B [E1].",
            "claims": [{"text": "A", "evidence": ["E1"]}, {"text": "B", "evidence": ["E1"]}],
            "insufficient_evidence": False,
        }


async def test_answers_run_reports_faithfulness() -> None:
    async with get_sessionmaker()() as db:
        run = await run_answers(
            db,
            embedder=HashingEmbeddings(),
            llm=AnswerAndJudgeLLM(),
            split="tune",
            dataset=load_dataset("v1"),
            limit=5,
        )
    m = run.metrics or {}
    assert run.status == "completed", run.error
    assert m["claims_judged"] == 10 and m["faithfulness"] == 0.5 and m["judge_errors"] == 0
    assert run.config["faithfulness_judge"] == "answer-and-judge"
