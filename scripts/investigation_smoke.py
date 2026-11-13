"""Live end-to-end investigation against running API + worker + MCP servers + Ollama.

Usage: uv run --project backend python scripts/investigation_smoke.py [--api http://localhost:8000]
Seeds nothing itself: run scripts/seed_cloudwatch.py first so the synthetic incident is fresh.
"""

import argparse
import pathlib
import secrets
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx

CORPUS = pathlib.Path(__file__).resolve().parent.parent / "evaluation/datasets/v1/corpus"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--github-repo", default=None, help="owner/name to connect (must be allowlisted on the server)")
    ap.add_argument("--no-cloudwatch", action="store_true", help="documents only (no live sources)")
    args = ap.parse_args()
    api = f"{args.api}/api/v1"
    c = httpx.Client(timeout=120)
    r = c.post(f"{api}/auth/register", json={"email": f"inv-{secrets.token_hex(4)}@example.com",
                                             "password": "investigation-smoke", "display_name": "Smoke"})
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    h["X-Workspace-Id"] = c.get(f"{api}/workspaces", headers=h).json()[0]["id"]
    print("tools/sync:", {k: (v if isinstance(v, str) else len(v)) for k, v in c.post(f"{api}/tools/sync", headers=h).json().items()})

    ids = []
    for f in sorted(CORPUS.glob("*.md")):
        data = f.read_bytes()
        src = "incident_report" if f.name.startswith("inc-") else ("architecture" if "architecture" in f.name else "runbook")
        u = c.post(f"{api}/documents/upload-url", headers=h, json={"filename": f.name, "mime_type": "text/markdown",
                   "size_bytes": len(data), "source_type": src, "service": "orders-api"}).json()
        c.put(u["upload_url"], content=data, headers=u["headers"]).raise_for_status()
        c.post(f"{api}/documents/complete-upload", headers=h, json={"document_id": u["document_id"]}).raise_for_status()
        ids.append(u["document_id"])
    while any(c.get(f"{api}/documents/{i}/status", headers=h).json()["status"] not in ("indexed", "failed") for i in ids):
        time.sleep(1)
    print(f"indexed {len(ids)} documents")

    if not args.no_cloudwatch:
        c.post(f"{api}/integrations", headers=h, json={"kind": "cloudwatch", "config": {
            "log_groups": ["/ecs/orders-api"], "namespaces": ["OpsPilot/OrdersApi"]}}).raise_for_status()
    if args.github_repo:
        c.post(f"{api}/integrations", headers=h, json={"kind": "github", "config": {"repositories": [args.github_repo]}}).raise_for_status()

    end = datetime.now(UTC) + timedelta(minutes=1)
    t0 = time.time()
    inv = c.post(f"{api}/investigations", headers=h, json={
        "question": "Investigate why orders-api response time increased after the latest deployment. Find evidence, possible causes and next steps.",
        "service": "orders-api", "environment": "production",
        "time_start": (end - timedelta(hours=2, minutes=30)).isoformat(), "time_end": end.isoformat()}).json()
    inv_id = inv["id"]
    seen = 0
    while True:
        frames = c.get(f"{api}/investigations/{inv_id}/events?follow=false", headers={**h, "Last-Event-ID": str(seen)}).text
        for fr in [x for x in frames.split("\n\n") if x.strip()]:
            lines = dict(line.split(": ", 1) for line in fr.splitlines() if ": " in line)
            seen = int(lines["id"])
            print(f"  [{time.time() - t0:5.1f}s] #{seen} {lines['event']}  {lines['data'][:150]}")
        state = c.get(f"{api}/investigations/{inv_id}", headers=h).json()["state"]
        if state in ("COMPLETED", "PARTIAL", "FAILED_LLM", "FAILED_RETRIEVAL", "FAILED_INVALID_PARAMS", "AWAITING_PARAMETERS"):
            break
        if time.time() - t0 > 600:
            print("timed out waiting")
            return 1
        time.sleep(2)

    inv = c.get(f"{api}/investigations/{inv_id}", headers=h).json()
    print(f"\nstate={inv['state']} in {time.time() - t0:.0f}s  plan={inv['plan']}  failed_steps={inv['failed_steps']}")
    ev = c.get(f"{api}/investigations/{inv_id}/evidence", headers=h).json()
    label = {e["id"]: e["label"] for e in ev}
    print(f"\nEVIDENCE ({len(ev)}):")
    for e in ev:
        print(f"  {e['label']:4} {e['source_system']:15} {e['title'][:90]}")
    rep = c.get(f"{api}/investigations/{inv_id}/report", headers=h)
    if rep.status_code != 200:
        print("no report", rep.text)
        return 1
    rep = rep.json()
    print("\nOVERVIEW:", rep["overview"])
    print("\nFACTS:")
    for f in rep["observed_facts"]:
        print("  -", f["text"], [label.get(i) for i in f["evidence_ids"]])
    print("\nHYPOTHESES:")
    for hyp in rep["hypotheses"]:
        print(f"  - [{hyp['status']}] {hyp['statement']}  sup={[label.get(i) for i in hyp['supporting_evidence_ids']]} con={[label.get(i) for i in hyp['contradicting_evidence_ids']]}")
        print(f"      why: {hyp['confidence_explanation']}")
        print(f"      missing: {hyp['missing_evidence']}")
    print("\nDIAGNOSTICS:", rep["recommended_diagnostics"])
    print("REMEDIATION:", rep["proposed_remediation"])
    print("UNKNOWNS:", rep["unknowns"])
    print("TOOLS:", rep["tool_summary"])
    print("REMOVED BY VALIDATION:")
    for r in rep.get("removed_by_validation", []):
        print(f"  - {r['kind']}: {r['text'][:120]!r} -> {r['reason']} (cited {r.get('cited')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
