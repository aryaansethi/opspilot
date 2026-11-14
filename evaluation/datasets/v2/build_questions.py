"""Dataset v2 = the 100 v1 questions + 121 new ones over 7 new documents.

Fields per question:
  relevant  (document, section heading) pairs that contain the answer
  match     "all" (default): every relevant section should be retrieved
            "any": ambiguous question; any ONE relevant section is a full hit
  kind      query style: lexical | semantic | multi | ambiguous | unanswerable
  topic     error | latency | database | deployment | other | none
  expected_facts  phrases that must appear verbatim in the relevant sections
                  (checked by evaluation/datasets/validate.py)
Split rule is unchanged from v1 (index % 10 in {1, 4, 7} -> tune), so the first
100 questions keep their v1 split.

Run: python evaluation/datasets/v2/build_questions.py
"""

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("v1q", HERE.parent / "v1" / "build_questions.py")
assert _spec and _spec.loader
v1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v1)

OR, PR, PA, AR, AA, NR, SR, IR = v1.OR, v1.PR, v1.PA, v1.AR, v1.AA, v1.NR, v1.SR, v1.IR
MEM, HTTP, DEP, DN43, DN28 = v1.MEM, v1.HTTP, v1.DEP, v1.DN43, v1.DN28
I18, I22, I27, I31, I34, I40, I44 = v1.I18, v1.I22, v1.I27, v1.I31, v1.I34, v1.I40, v1.I44
PLAT, OBS, DB, CACHE = v1.PLAT, v1.OBS, v1.DB, v1.CACHE
DBF, DEPF, LAT, ERRS = "database-failover-runbook", "deployment-failures-guide", "latency-troubleshooting-guide", "error-codes-reference"
I47, I49, I52 = "inc-2026-047-db-failover-connection-storm", "inc-2026-049-exec-format-error", "inc-2026-052-search-latency-cold-cache"
HC = "Tasks fail health checks and the deployment never finishes"

# Approximate topic for the 100 questions carried over from v1, by their first relevant document.
V1_TOPIC = {OR: "database", PR: "error", PA: "other", AR: "error", AA: "other", NR: "error", SR: "error",
            IR: "database", MEM: "other", HTTP: "error", DEP: "deployment", DN43: "deployment", DN28: "deployment",
            I18: "latency", I22: "error", I27: "latency", I31: "latency", I34: "error", I40: "other",
            I44: "deployment", PLAT: "other", OBS: "other", DB: "database", CACHE: "latency"}

# (question, relevant, facts, kind, topic, match)
NEW = [
    # ---- error investigation
    ("What does INV_RESERVATION_CONFLICT mean and what should the client do?", [(ERRS, "Orders and inventory")], ["another order holds the same SKU", "retry once"], "lexical", "error", "all"),
    ("What is AUTH_TOKEN_EXPIRED?", [(ERRS, "Identity")], ["15 minute lifetime"], "lexical", "error", "all"),
    ("Which error code means a search query started with a wildcard?", [(ERRS, "Search and notifications")], ["SRCH_QUERY_TOO_BROAD"], "semantic", "error", "all"),
    ("What happens to a notification when a template variable is missing?", [(ERRS, "Search and notifications")], ["goes to the DLQ"], "semantic", "error", "all"),
    ("Where do application error codes appear?", [(ERRS, "Application Error Codes Reference")], ["code=<CODE>"], "lexical", "error", "all"),
    ("What does code=PAY_GATEWAY_502 in a log line mean?", [(ERRS, "Payments"), (PR, "Card authorization failures")], ["bad gateway"], "lexical", "error", "any"),
    ("A client reused an idempotency key with a different body; which code is returned?", [(ERRS, "Payments"), (PR, "Idempotency key conflicts")], ["IDEMP_409"], "semantic", "error", "any"),
    ("ERR_POOL_TIMEOUT: how long does orders-api wait for a database connection?", [(ERRS, "Orders and inventory")], ["30 seconds"], "lexical", "error", "all"),
    ("What should a client do when its access token is too old?", [(ERRS, "Identity")], ["refresh"], "semantic", "error", "all"),
    ("Which service rejects queries that start with a wildcard character?", [(ERRS, "Search and notifications"), (SR, "Slow queries")], ["search-api"], "semantic", "error", "any"),
    ("What do HTTP 500 responses indicate?", [(HTTP, "Application 500 errors")], ["application itself"], "semantic", "error", "all"),
    ("What does yellow search cluster health mean?", [(SR, "Cluster health yellow or red")], ["replica shards are unassigned"], "semantic", "error", "all"),
    # ---- database failures
    ("What does 'cannot execute UPDATE in a read-only transaction' mean?", [(DBF, "Read-only transaction errors")], ["writing to a replica"], "lexical", "database", "all"),
    ("What does 'remaining connection slots are reserved' indicate?", [(DBF, "Connection storm after failover")], ["exhaust"], "lexical", "database", "all"),
    ("What does 'could not extend file' mean on the database?", [(DBF, "Disk full on the primary")], ["primary volume is full"], "lexical", "database", "all"),
    ("What lock_timeout should migration sessions use?", [(DBF, "Lock timeouts during migrations")], ["5s"], "lexical", "database", "all"),
    ("Why can a schema migration block every query on a table?", [(DBF, "Lock timeouts during migrations")], ["ACCESS EXCLUSIVE"], "semantic", "database", "all"),
    ("What usually causes WAL growth that fills the database disk?", [(DBF, "Disk full on the primary")], ["inactive replication slots"], "semantic", "database", "all"),
    ("After a failover, how do I get services writing to the right database again?", [(DBF, "Read-only transaction errors")], ["recycle the pools"], "semantic", "database", "all"),
    ("How can we stop every service reconnecting at once after a failover?", [(DBF, "Connection storm after failover"), (I47, "Follow-up actions")], ["jitter"], "semantic", "database", "any"),
    ("What happened in INC-2026-047?", [(I47, "Summary")], ["34 minutes"], "lexical", "database", "all"),
    ("Why did orders-api fail after the October database failover?", [(I47, "Root cause")], ["old primary"], "semantic", "database", "all"),
    ("How was the failover connection storm resolved?", [(I47, "Resolution")], ["restarted in sequence"], "semantic", "database", "all"),
    ("Why might writes fail while reads still work on the primary database?", [(DBF, "Disk full on the primary")], ["reads continue"], "semantic", "database", "all"),
    ("What is minimumIdle and why lower it?", [(DBF, "Connection storm after failover")], ["minimumIdle"], "lexical", "database", "all"),
    ("What happens to traffic when a migration is waiting for a lock?", [(DBF, "Lock timeouts during migrations")], ["queuing all traffic"], "semantic", "database", "all"),
    ("Which instance class does payments-db use?", [(PA, "Dependencies")], ["db.r6g.large"], "lexical", "database", "all"),
    ("Where must reads that need fresh data go?", [(DB, "Replica lag")], ["primary"], "semantic", "database", "all"),
    ("What replica lag triggers an alert?", [(DB, "Replica lag")], ["30 seconds"], "lexical", "database", "all"),
    ("How many database connections are allocated to inventory-service?", [(DB, "Connection limits")], ["120"], "lexical", "database", "all"),
    ("Which system view shows long-running Postgres queries?", [(DB, "Finding long-running queries")], ["pg_stat_activity"], "lexical", "database", "all"),
    # ---- deployment failures
    ("What does CannotPullContainerError mean?", [(DEPF, "CannotPullContainerError")], ["could not download the image"], "lexical", "deployment", "all"),
    ("What causes 'ResourceInitializationError: unable to pull secrets or registry auth'?", [(DEPF, "ResourceInitializationError for secrets")], ["cannot read a Secrets Manager secret"], "lexical", "deployment", "all"),
    ("What does 'exec format error' at container start mean?", [(DEPF, "exec format error")], ["different CPU architecture"], "lexical", "deployment", "all"),
    ("Which IAM permissions does ECS need to pull images from ECR?", [(DEPF, "CannotPullContainerError")], ["ecr:GetAuthorizationToken"], "lexical", "deployment", "all"),
    ("Why do deployments roll back after 10 failed tasks?", [(DEPF, HC)], ["circuit breaker"], "semantic", "deployment", "all"),
    ("How fast must the health check path respond?", [(DEPF, HC)], ["5 second timeout"], "semantic", "deployment", "all"),
    ("What should I check when new ECS tasks keep failing the load balancer health check?", [(DEPF, HC)], ["container logs"], "semantic", "deployment", "all"),
    ("How do I roll back a deployment by hand after a failed release?", [(DEPF, "Rolling back"), (DEP, "Manual rollback")], ["previous task definition"], "semantic", "deployment", "any"),
    ("Which secret store do task definitions read secrets from?", [(DEPF, "ResourceInitializationError for secrets")], ["Secrets Manager"], "semantic", "deployment", "all"),
    ("Why was the catalog-service deployment stuck in October?", [(I49, "Root cause")], ["amd64-only image"], "semantic", "deployment", "all"),
    ("Were customers affected by the exec format error incident?", [(I49, "Summary")], ["customers were not affected"], "semantic", "deployment", "all"),
    ("How did the team fix the CPU architecture mismatch in catalog builds?", [(I49, "Resolution")], ["buildx"], "semantic", "deployment", "all"),
    ("What CI check was added after the missing environment variable incident?", [(I44, "Follow-up actions")], ["Validate required environment variables"], "semantic", "deployment", "all"),
    ("What are the deployment pipeline stages?", [(DEP, "Pipeline stages")], ["image scan"], "semantic", "deployment", "all"),
    ("How long does the canary run?", [(DEP, "Canary releases")], ["15 minutes"], "lexical", "deployment", "all"),
    ("Which release upgraded the PostgreSQL JDBC driver?", [(DN43, "Changes")], ["42.7"], "lexical", "deployment", "all"),
    ("When was orders-api 4.3 released?", [(DN43, "Release notes: orders-api 4.3")], ["2026-11-12"], "lexical", "deployment", "all"),
    ("Which gateway SDK version did payments 2.8 move to?", [(DN28, "Changes")], ["6.1"], "lexical", "deployment", "all"),
    ("What new endpoint did orders-api 4.3 add?", [(DN43, "Changes")], ["timeline"], "semantic", "deployment", "all"),
    # ---- latency
    ("What does RejectedExecutionException indicate?", [(LAT, "Thread pool exhaustion")], ["thread pool is full"], "lexical", "latency", "all"),
    ("Why does search get slow right after each deployment?", [(I52, "Root cause"), (LAT, "Cold caches after a deployment")], ["empty"], "semantic", "latency", "any"),
    ("How far did search p95 rise after deployments in INC-2026-052?", [(I52, "Summary")], ["1.8 s"], "lexical", "latency", "all"),
    ("What deployment change fixed the post-deploy search latency?", [(I52, "Resolution")], ["25 percent of tasks"], "semantic", "latency", "all"),
    ("If p50 latency is stable but p95 rises, what does that suggest?", [(LAT, "p95 versus p50")], ["subset of requests"], "semantic", "latency", "all"),
    ("Requests slow down as lists grow and traces show the same SQL repeated hundreds of times. What is this?", [(LAT, "N+1 queries")], ["N+1"], "semantic", "latency", "all"),
    ("Outbound calls sometimes take an extra 5 seconds; what is a likely cause?", [(LAT, "DNS resolution delays")], ["DNS lookups are timing out"], "semantic", "latency", "all"),
    ("Should I just increase the thread pool when requests are rejected?", [(LAT, "Thread pool exhaustion")], ["add a timeout to that call"], "semantic", "latency", "all"),
    ("How can we avoid slow responses from empty caches after a deploy?", [(LAT, "Cold caches after a deployment")], ["Warm critical caches"], "semantic", "latency", "all"),
    ("What is the catalog cache TTL?", [(CACHE, "Catalog Cache Architecture")], ["15 minute"], "semantic", "latency", "all"),
    ("Below what cache hit ratio does the catalog database get extra load?", [(CACHE, "Eviction behaviour")], ["80 percent"], "semantic", "latency", "all"),
    ("What is the load balancer idle timeout?", [(HTTP, "502 Bad Gateway")], ["60 seconds"], "lexical", "latency", "all"),
    # ---- other facts
    ("What does the reconciliation job compare stock against?", [(IR, "Nightly reconciliation job")], ["warehouse system"], "semantic", "other", "all"),
    ("How much memory does the reconciliation task get?", [(IR, "Nightly reconciliation job")], ["2 GB"], "semantic", "other", "all"),
    ("How many tasks does payments-api run in production?", [(PA, "Overview")], ["4 tasks"], "semantic", "other", "all"),
    ("Which ElastiCache node type backs the catalog cache?", [(CACHE, "Catalog Cache Architecture")], ["cache.r7g.large"], "lexical", "other", "all"),
    ("How many data nodes does the search cluster have?", [(SR, "Cluster health yellow or red")], ["3 data nodes"], "semantic", "other", "all"),
    ("After how many days are search log indices deleted now?", [(I34, "Follow-up actions")], ["14 days"], "semantic", "other", "all"),
    ("How long did INC-2026-034 last?", [(I34, "INC-2026-034: Search returning errors after cluster turned red")], ["1 hour 20 minutes"], "lexical", "other", "all"),
    ("What severity was the delayed password reset email incident?", [(I27, "INC-2026-027: Password reset emails delayed by two hours")], ["SEV-3"], "lexical", "other", "all"),
    ("When did the auth signing key rotation incident happen?", [(I22, "INC-2026-022: Logins rejected after signing key rotation")], ["2026-04-02"], "lexical", "other", "all"),
    ("How long did the payment authorization timeout incident last?", [(I18, "INC-2026-018: Payment authorization timeouts")], ["38 minutes"], "lexical", "other", "all"),
    ("What share of card authorizations failed in INC-2026-018?", [(I18, "Summary")], ["9 percent"], "lexical", "other", "all"),
    ("Which follow-ups came from the payment timeout incident?", [(I18, "Follow-up actions")], ["Load test timeout changes"], "semantic", "other", "all"),
    ("What follow-up came out of the signing key rotation incident?", [(I22, "Follow-up actions")], ["at least 2 hours"], "semantic", "other", "all"),
    ("How long were no emails sent during INC-2026-044?", [(I44, "Summary")], ["25 minutes"], "lexical", "other", "all"),
    ("What alert threshold was set for payment authorization failures?", [(I18, "Follow-up actions")], ["3 percent"], "semantic", "other", "all"),
    ("Who owns notifications-worker?", [(PLAT, "Services and owners"), (NR, "Notifications Worker Runbook")], ["Growth Platform team"], "semantic", "other", "any"),
    ("Which team owns search-api?", [(PLAT, "Services and owners"), (SR, "Search API Runbook")], ["Discovery team"], "semantic", "other", "any"),
    ("What is the availability target for payments?", [(PLAT, "Service level objectives")], ["99.95 percent"], "semantic", "other", "all"),
    ("What does auth-service depend on?", [(AA, "Dependencies")], ["notifications-worker"], "semantic", "other", "all"),
    ("Does auth-service call payments-api?", [(AA, "Dependencies")], ["no dependency on orders-api or payments-api"], "semantic", "other", "all"),
    ("How long are refresh tokens valid?", [(AA, "Overview")], ["30 days"], "semantic", "other", "all"),
    # ---- multi-section (all sections needed)
    ("orders-api logs say 'read-only transaction' and then 'remaining connection slots are reserved'; explain both.", [(DBF, "Read-only transaction errors"), (DBF, "Connection storm after failover")], ["replica", "max_connections"], "multi", "database", "all"),
    ("The catalog deploy rolled back; what does the circuit breaker do and what caused INC-2026-049?", [(DEPF, HC), (I49, "Root cause")], ["10 failed tasks", "amd64"], "multi", "deployment", "all"),
    ("What is the shared database connection limit and how did INC-2026-047 exceed it?", [(DB, "Connection limits"), (I47, "Root cause")], ["400"], "multi", "database", "all"),
    ("What is the search p95 objective and how far over it did INC-2026-052 go?", [(PLAT, "Service level objectives"), (I52, "Summary")], ["500 ms", "1.8 s"], "multi", "latency", "all"),
    ("For a failed deploy, how do I roll back manually and what stage does a rollback skip?", [(DEPF, "Rolling back"), (DEP, "Manual rollback")], ["skip the canary"], "multi", "deployment", "all"),
    ("Which error code and which runbook section cover orders-api pool exhaustion?", [(ERRS, "Orders and inventory"), (OR, "Database connection exhaustion")], ["ERR_POOL_TIMEOUT"], "multi", "error", "all"),
    ("Explain IDEMP_409 and why the idempotency Redis must not be flushed.", [(ERRS, "Payments"), (PR, "Idempotency key conflicts")], ["double charges"], "multi", "error", "all"),
    ("What is AUTH_INVALID_KID and how long do services cache the JWKS?", [(ERRS, "Identity"), (AR, "Token validation errors")], ["1 hour"], "multi", "error", "all"),
    ("Which error code sends notifications to the DLQ, and after how many failures?", [(ERRS, "Search and notifications"), (NR, "Poison messages")], ["5 times"], "multi", "error", "all"),
    ("What thread pool error follows slow downstream calls, and what timeout bounds card gateway calls?", [(LAT, "Thread pool exhaustion"), (PA, "Timeouts and retries")], ["8 second timeout"], "multi", "latency", "all"),
    ("Which log group and which alarm should I check for orders-api latency?", [(OBS, "Logs"), (OBS, "Alarms")], ["p95-latency"], "multi", "latency", "all"),
    ("What is the canary rollback rule, and what did the deploy notes warn about orders-api 4.3?", [(DEP, "Canary releases"), (DN43, "Known risks")], ["not been load tested"], "multi", "deployment", "all"),
    # ---- ambiguous (any one relevant section is a full hit)
    ("Why is checkout slow?", [(I31, "Root cause"), (OR, "Elevated latency after a deployment"), (LAT, "p95 versus p50")], [], "ambiguous", "latency", "any"),
    ("Deploy failed, what now?", [(DEPF, HC), (DEPF, "Rolling back"), (DEP, "Manual rollback")], [], "ambiguous", "deployment", "any"),
    ("Database errors after maintenance", [(DBF, "Read-only transaction errors"), (DBF, "Connection storm after failover"), (I47, "Summary")], [], "ambiguous", "database", "any"),
    ("Users can't log in", [(AR, "Token validation errors"), (AR, "Account lockout"), (AR, "Login latency spikes"), (I22, "Summary")], [], "ambiguous", "error", "any"),
    ("Emails are not going out", [(NR, "Queue backlog"), (NR, "Required configuration"), (I44, "Summary"), (NR, "Email provider throttling")], [], "ambiguous", "error", "any"),
    ("search is broken", [(SR, "Cluster health yellow or red"), (I34, "Summary"), (SR, "Slow queries")], [], "ambiguous", "error", "any"),
    ("memory problems", [(MEM, "JVM heap exhaustion"), (MEM, "Container killed by the kernel")], [], "ambiguous", "other", "any"),
    ("payments failing", [(PR, "Card authorization failures"), (I18, "Summary")], [], "ambiguous", "error", "any"),
    ("high latency after a release", [(OR, "Elevated latency after a deployment"), (LAT, "Cold caches after a deployment"), (I52, "Summary")], [], "ambiguous", "latency", "any"),
    ("disk full", [(DBF, "Disk full on the primary"), (I34, "Root cause")], [], "ambiguous", "database", "any"),
    ("stock numbers look wrong", [(IR, "Nightly reconciliation job")], [], "ambiguous", "other", "any"),
    ("timeouts everywhere", [(HTTP, "504 Gateway Timeout"), (LAT, "p95 versus p50"), (LAT, "DNS resolution delays")], [], "ambiguous", "latency", "any"),
    # ---- unanswerable
    ("What was the root cause of INC-2026-060?", [], [], "unanswerable", "none", "all"),
    ("How do I scale the OpenSearch cluster to 6 nodes?", [], [], "unanswerable", "none", "all"),
    ("What is the backup retention period for payments-db?", [], [], "unanswerable", "none", "all"),
    ("Which on-call engineer handled INC-2026-047?", [], [], "unanswerable", "none", "all"),
    ("What Kafka broker version runs in production?", [], [], "unanswerable", "none", "all"),
    ("How do I enable mutual TLS between services?", [], [], "unanswerable", "none", "all"),
    ("Which feature flags are enabled for checkout in production?", [], [], "unanswerable", "none", "all"),
    ("What was the revenue impact of INC-2026-018?", [], [], "unanswerable", "none", "all"),
    ("How do I restore the catalog cache from a snapshot?", [], [], "unanswerable", "none", "all"),
    ("What is the maximum upload size for product images?", [], [], "unanswerable", "none", "all"),
    ("Which Grafana dashboard shows search latency?", [], [], "unanswerable", "none", "all"),
    ("How often is the auth-db password rotated?", [], [], "unanswerable", "none", "all"),
    ("Which load testing tool does the team use?", [], [], "unanswerable", "none", "all"),
    ("How many ECS clusters exist?", [], [], "unanswerable", "none", "all"),
    ("What is the recovery point objective for orders data?", [], [], "unanswerable", "none", "all"),
]


# Two v1 expected facts were not verbatim in the corpus (found by validate.py). v1 stays frozen;
# v2 uses wording that appears in the documents.
V1_FACT_FIXES = {
    "What does java.lang.OutOfMemoryError: Java heap space mean?": ["is full"],
    "What is the X-Request-Id header for?": ["followed across services"],
}


def main() -> None:
    rows = []
    for q, rel, facts, kind in v1.Q:
        topic = "none" if not rel else V1_TOPIC[rel[0][0]]
        rows.append((q, rel, V1_FACT_FIXES.get(q, facts), kind, topic, "all"))
    rows.extend(NEW)
    out = HERE / "questions.jsonl"
    with out.open("w") as f:
        for i, (q, rel, facts, kind, topic, match) in enumerate(rows, start=1):
            f.write(json.dumps({
                "id": f"q{i:03d}", "question": q,
                "relevant": [{"document": d, "section": s} for d, s in rel],
                "match": match, "answerable": bool(rel), "expected_facts": facts,
                "kind": kind, "topic": topic,
                "split": "tune" if i % 10 in (1, 4, 7) else "test",
            }) + "\n")
    print(f"wrote {len(rows)} questions to {out}")


if __name__ == "__main__":
    main()
