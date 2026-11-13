"""End-to-end smoke test against a running API + worker (real Ollama models).

Usage: uv run --project backend python scripts/smoke_test.py [--api http://localhost:8000]
Registers a throwaway user, uploads the v1 demo corpus, waits for indexing,
then runs lexical / vector / hybrid searches and one grounded question.
"""

import argparse
import pathlib
import secrets
import sys
import time

import httpx

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "evaluation/datasets/v1/corpus"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--skip-ask", action="store_true")
    ap.add_argument("--rerank", action="store_true", help="also run hybrid + cross-encoder rerank")
    args = ap.parse_args()
    api = f"{args.api}/api/v1"
    c = httpx.Client(timeout=300)

    email = f"smoke-{secrets.token_hex(4)}@example.com"
    r = c.post(
        f"{api}/auth/register",
        json={"email": email, "password": "smoke-test-password", "display_name": "Smoke"},
    )
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ws = c.get(f"{api}/workspaces", headers=h).json()[0]["id"]
    h["X-Workspace-Id"] = ws
    print(f"user {email} workspace {ws}")

    ids = []
    for f in sorted(CORPUS.glob("*.md")):
        data = f.read_bytes()
        src = (
            "incident_report"
            if f.name.startswith("inc-")
            else ("architecture" if "architecture" in f.name else "runbook")
        )
        u = c.post(
            f"{api}/documents/upload-url",
            headers=h,
            json={
                "filename": f.name,
                "mime_type": "text/markdown",
                "size_bytes": len(data),
                "source_type": src,
                "service": "orders-api",
                "environment": "production",
            },
        ).json()
        c.put(u["upload_url"], content=data, headers=u["headers"]).raise_for_status()
        c.post(
            f"{api}/documents/complete-upload", headers=h, json={"document_id": u["document_id"]}
        ).raise_for_status()
        ids.append(u["document_id"])
    print(f"uploaded {len(ids)} documents; waiting for worker...")

    deadline = time.time() + 300
    while time.time() < deadline:
        sts = [c.get(f"{api}/documents/{i}/status", headers=h).json() for i in ids]
        if all(s["status"] in ("indexed", "failed") for s in sts):
            break
        time.sleep(2)
    for i, s in zip(ids, sts, strict=True):
        print(f"  {i}: {s['status']} chunks={s['chunk_count']} {s.get('error') or ''}")
    if any(s["status"] != "indexed" for s in sts):
        return 1

    runs = [
        ("lexical", "ERR_POOL_TIMEOUT", False),
        ("vector", "why did checkout get slow after the release", False),
        ("hybrid", "connection pool size changed latency", False),
    ]
    if args.rerank:
        runs.append(("hybrid", "connection pool size changed latency", True))
    for mode, q, rr in runs:
        res = c.post(
            f"{api}/search/debug",
            headers=h,
            json={"query": q, "mode": mode, "top_k": 3, "rerank": rr},
        ).json()
        print(
            f"\n[{mode}{'+rerank' if rr else ''}] {q!r}  ({res['latency_ms']} ms, timings {res['timings_ms']})"
        )
        for x in res["results"]:
            d = x["debug"]
            print(
                f"  {x['document_title'][:40]:40} | {str(x['section_path'])[:45]:45} | lex={d['lexical_rank']} vec={d['vector_rank']} rrf={d['rrf_score']:.4f} rerank={d['rerank_score']}"
            )

    if not args.skip_ask:
        q = "Why did checkout time out after release 4.2 and how was it fixed?"
        t = time.time()
        a = c.post(f"{api}/ask", headers=h, json={"question": q})
        print(f"\n[ask] {q}  ({time.time() - t:.1f}s) status={a.status_code}")
        body = a.json()
        if a.status_code != 200:
            print(body)
            return 1
        print("answer:", body["answer"])
        print(
            "insufficient_evidence:",
            body["insufficient_evidence"],
            "| removed:",
            body["removed_invalid_citations"],
        )
        for i, ev in enumerate(body["citations"], 1):
            print(f"  [{i}] {ev['title']} > {ev['metadata']['section_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
