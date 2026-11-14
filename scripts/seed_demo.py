"""Seed a ready-to-demo workspace. Safe to run repeatedly (idempotent).

Creates (or signs in to) the demo account, uploads the synthetic v1 corpus, writes the
SYNTHETIC CloudWatch incident into LocalStack, and connects CloudWatch to the workspace.
GitHub is connected only when repositories are configured (--github-repos or
GITHUB_ALLOWED_REPOS); without a token the rest of the demo still works.

Everything here is local and free: LocalStack stands in for AWS, and no real AWS account
or GitHub token is needed.

Usage (from the repository root):
  native API:      uv run --project backend python scripts/seed_demo.py
  Compose stack:   docker compose --profile app run --rm seed   (runs this inside the backend image)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = ROOT / "evaluation/datasets/v1/corpus"
# Local demo login, documented in README.md. Not a secret: the stack only listens on localhost.
DEMO_EMAIL = "demo@opspilot.dev"
DEMO_PASSWORD = "opspilot-demo-2026"  # noqa: S105
SERVICES = (
    "orders-api",
    "payments-api",
    "auth-service",
    "inventory-service",
    "search-api",
    "notifications-worker",
)


def log(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def source_type(name: str) -> str:
    if name.startswith("inc-"):
        return "incident_report"
    if "architecture" in name:
        return "architecture"
    if "runbook" in name or "guide" in name or "deploy-notes" in name:
        return "runbook"
    return "other"


def service_for(name: str) -> str | None:
    for s in SERVICES:
        if s.split("-")[0] in name:
            return s
    return None


def sign_in(c: httpx.Client, api: str) -> dict[str, str]:
    r = c.post(f"{api}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    if r.status_code == 401:
        r = c.post(
            f"{api}/auth/register",
            json={
                "email": DEMO_EMAIL,
                "password": DEMO_PASSWORD,
                "display_name": "Demo Engineer",
                "workspace_name": "Demo workspace",
            },
        )
        log(f"created demo account {DEMO_EMAIL}")
    else:
        log(f"signed in as {DEMO_EMAIL}")
    r.raise_for_status()
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    ws = c.get(f"{api}/workspaces", headers=h).json()[0]
    h["X-Workspace-Id"] = ws["id"]
    log(f"workspace '{ws['name']}' ({ws['id']})")
    return h


def put_object(
    c: httpx.Client, url: str, headers: dict[str, str], data: bytes, s3_endpoint: str | None
) -> None:
    """PUT to the presigned URL. Inside Compose the URL's host (localhost:4566) isn't reachable,
    so send the request to the internal endpoint but keep the signed Host header."""
    if s3_endpoint:
        signed = urlsplit(url)
        target = urlsplit(s3_endpoint)
        url = urlunsplit((target.scheme, target.netloc, signed.path, signed.query, ""))
        headers = {**headers, "Host": signed.netloc}
    c.put(url, content=data, headers=headers).raise_for_status()


def upload_corpus(
    c: httpx.Client, api: str, h: dict[str, str], corpus: pathlib.Path, s3_endpoint: str | None
) -> None:
    existing = {
        d["filename"]: d
        for d in c.get(f"{api}/documents", headers=h, params={"limit": 100}).json()["items"]
    }
    files = sorted(corpus.glob("*.md"))
    new_ids = []
    for f in files:
        if f.name in existing and existing[f.name]["status"] != "failed":
            continue
        data = f.read_bytes()
        u = c.post(
            f"{api}/documents/upload-url",
            headers=h,
            json={
                "filename": f.name,
                "mime_type": "text/markdown",
                "size_bytes": len(data),
                "source_type": source_type(f.name),
                "service": service_for(f.name),
                "environment": "production",
            },
        )
        u.raise_for_status()
        target = u.json()
        put_object(c, target["upload_url"], target["headers"], data, s3_endpoint)
        c.post(
            f"{api}/documents/complete-upload",
            headers=h,
            json={"document_id": target["document_id"]},
        ).raise_for_status()
        new_ids.append(target["document_id"])
    kept = len(files) - len(new_ids)
    log(f"corpus: {len(files)} documents, {len(new_ids)} uploaded now, {kept} already present")

    deadline = time.time() + 600
    while new_ids and time.time() < deadline:
        sts = [c.get(f"{api}/documents/{i}/status", headers=h).json() for i in new_ids]
        pending = [s for s in sts if s["status"] not in ("indexed", "failed")]
        if not pending:
            failed = [s for s in sts if s["status"] == "failed"]
            log(f"indexing done: {len(sts) - len(failed)} indexed, {len(failed)} failed")
            for s in failed:
                log(f"  failed: {s.get('error')}")
            break
        time.sleep(3)
    else:
        if new_ids:
            log("indexing still running after 10 min; is the worker up and Ollama reachable?")


def seed_cloudwatch() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    for p in (ROOT / "backend", pathlib.Path("/app")):
        if (p / "mcp_servers").is_dir():
            sys.path.insert(0, str(p))
    import seed_cloudwatch  # noqa: PLC0415

    seed_cloudwatch.main()


def connect(
    c: httpx.Client, api: str, h: dict[str, str], kind: str, config: dict[str, object]
) -> None:
    current = {i["kind"]: i for i in c.get(f"{api}/integrations", headers=h).json()}
    if kind in current:
        integ = current[kind]
        log(f"{kind}: already connected")
    else:
        r = c.post(f"{api}/integrations", headers=h, json={"kind": kind, "config": config})
        if r.status_code >= 400:
            log(f"{kind}: could not connect ({r.status_code}) {r.text[:200]}")
            return
        integ = r.json()
        log(f"{kind}: connected")
    t = c.post(f"{api}/integrations/{integ['id']}/test", headers=h)
    if t.status_code < 400:
        res = t.json()
        note = f" ({res['last_error']})" if res.get("last_error") else ""
        log(f"{kind}: connection test -> {res['status']}{note}")
    else:
        log(f"{kind}: connection test failed ({t.status_code}) {t.text[:200]}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--api",
        default=os.environ.get("SEED_API_URL", "http://localhost:8000"),
        help="API origin (default %(default)s)",
    )
    ap.add_argument(
        "--corpus",
        type=pathlib.Path,
        default=pathlib.Path(os.environ.get("SEED_CORPUS_DIR", DEFAULT_CORPUS)),
    )
    ap.add_argument(
        "--s3-endpoint",
        default=os.environ.get("SEED_S3_ENDPOINT"),
        help="send uploads here instead of the presigned host (Compose: http://localstack:4566)",
    )
    ap.add_argument(
        "--github-repos",
        default=os.environ.get("GITHUB_ALLOWED_REPOS", ""),
        help="owner/name,... to connect (needs GITHUB_TOKEN on the GitHub MCP server)",
    )
    ap.add_argument(
        "--skip-cloudwatch", action="store_true", help="don't write synthetic CloudWatch data"
    )
    args = ap.parse_args()
    api = f"{args.api.rstrip('/')}/api/v1"

    with httpx.Client(timeout=120) as c:
        for _ in range(60):
            try:
                if c.get(f"{args.api.rstrip('/')}/healthz").status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        else:
            log(f"API at {args.api} is not reachable")
            return 1

        h = sign_in(c, api)
        upload_corpus(c, api, h, args.corpus, args.s3_endpoint)

        if not args.skip_cloudwatch:
            seed_cloudwatch()
            log("cloudwatch: SYNTHETIC incident written to LocalStack (deploy 60 min ago)")
        connect(
            c,
            api,
            h,
            "cloudwatch",
            {"log_groups": ["/ecs/orders-api"], "namespaces": ["OpsPilot/OrdersApi"]},
        )

        repos = [r.strip() for r in args.github_repos.split(",") if r.strip()]
        if repos:
            connect(c, api, h, "github", {"repositories": repos})
        else:
            log("github: skipped (set GITHUB_TOKEN and GITHUB_ALLOWED_REPOS to enable it)")

    log(f"done. Sign in at http://localhost:3000 with {DEMO_EMAIL} / {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
