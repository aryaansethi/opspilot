"""Source of truth for the v1 question set; writes questions.jsonl.

Each question lists the (document, section heading) pairs that contain its answer.
A retrieved chunk is relevant if it comes from that document and its section path
ends with that heading. `kind` describes what the question stresses:
  lexical      exact identifiers / error codes
  semantic     paraphrased symptoms, little word overlap
  multi        answer needs two sections
  unanswerable not in the corpus (expect abstention)
Split: deterministic, ~30% "tune" (for choosing settings), ~70% "test" (reported).
Run: python evaluation/datasets/v1/build_questions.py
"""

import json
from pathlib import Path

OR, PR, PA = "orders-api-runbook", "payments-api-runbook", "payments-api-architecture"
AR, AA = "auth-service-runbook", "auth-service-architecture"
NR, SR, IR = "notifications-worker-runbook", "search-api-runbook", "inventory-service-runbook"
MEM, HTTP, DEP = "memory-troubleshooting-guide", "http-5xx-troubleshooting-guide", "deployment-guide"
DN43, DN28 = "deploy-notes-orders-api-4-3", "deploy-notes-payments-api-2-8"
I18, I22, I27 = "inc-2026-018-payments-gateway-timeouts", "inc-2026-022-auth-key-rotation", "inc-2026-027-notifications-backlog"
I31, I34, I40, I44 = "inc-2026-031-checkout-timeouts", "inc-2026-034-search-cluster-red", "inc-2026-040-inventory-oom", "inc-2026-044-missing-env-var"
PLAT, OBS, DB, CACHE = "platform-architecture-overview", "observability-guide", "database-operations-runbook", "cache-architecture"

Q = [
    # ---- lexical: exact identifiers and codes
    ("What does PAY_GATEWAY_502 mean?", [(PR, "Card authorization failures")], ["external card gateway returned a bad gateway response"], "lexical"),
    ("When is IDEMP_409 returned?", [(PR, "Idempotency key conflicts")], ["same idempotency key but a different amount"], "lexical"),
    ("What causes AUTH_INVALID_KID errors?", [(AR, "Token validation errors"), (I22, "Root cause")], ["key ID that the validating service does not know"], "lexical"),
    ("What does SQLSTATE 40P01 indicate in inventory-service?", [(IR, "Stock reservation deadlocks")], ["deadlocks"], "lexical"),
    ("What does ERR_POOL_TIMEOUT indicate?", [(OR, "Database connection exhaustion")], ["pool"], "lexical"),
    ("What is a CircuitBreakingException in search-api?", [(SR, "Circuit breaker exceptions")], ["exceed the JVM memory limit"], "lexical"),
    ("What does exit code 137 OOMKilled mean?", [(MEM, "Container killed by the kernel")], ["exceeded its memory limit"], "lexical"),
    ("What does java.lang.OutOfMemoryError: Java heap space mean?", [(MEM, "JVM heap exhaustion")], ["heap is full"], "lexical"),
    ("What is the payments.fallback_acquirer flag used for?", [(PR, "Card authorization failures")], ["fallback acquirer"], "lexical"),
    ("What is POST /internal/jwks/refresh used for?", [(AR, "Token validation errors")], ["Force a refresh"], "lexical"),
    ("Which SQS queue holds gateway webhooks?", [(PR, "Webhook backlog")], ["payments-webhooks"], "lexical"),
    ("Where is the payments gateway key stored in Secrets Manager?", [(PR, "Rotating the gateway API key")], ["payments/gateway-key"], "lexical"),
    ("What is notifications-dlq?", [(NR, "Poison messages")], ["fail 5 times"], "lexical"),
    ("What does the reindex-products job do and how long does it take?", [(SR, "Reindexing")], ["40 minutes"], "lexical"),
    ("Which Kafka topic does inventory-service consume?", [(IR, "Consumer lag on inventory-events")], ["inventory-events"], "lexical"),
    ("What does the log line 'Throttling: Maximum sending rate exceeded' mean?", [(NR, "Email provider throttling")], ["SES"], "lexical"),
    ("What does KeyError: 'SMTP_FROM_ADDRESS' indicate?", [(I44, "Root cause"), (NR, "Required configuration")], ["missing"], "lexical"),
    ("What is ApproximateAgeOfOldestMessage alert threshold for notifications?", [(NR, "Queue backlog")], ["600 seconds"], "lexical"),
    ("What is hikaricp.connections.active used for?", [(OR, "Database connection exhaustion")], ["active connections"], "lexical"),
    ("What was spring.datasource.hikari.maximum-pool-size changed to in orders-api 4.3?", [(DN43, "Changes")], ["50 to 10"], "lexical"),
    ("What is the X-Request-Id header for?", [(OBS, "Request tracing"), (HTTP, "Application 500 errors")], ["follow a request"], "lexical"),
    ("What is the naming convention for CloudWatch log groups?", [(OBS, "Logs")], ["/ecs/<service>"], "lexical"),
    ("What is the metrics namespace convention?", [(OBS, "Metrics")], ["OpsPilot/<ServiceName>"], "lexical"),
    ("What is pg_terminate_backend used for and when?", [(DB, "Finding long-running queries")], ["only after confirming it is not a migration"], "lexical"),
    ("What is max_connections on the shared PostgreSQL cluster?", [(PLAT, "Shared database cluster"), (DB, "Connection limits")], ["400"], "lexical"),
    ("Which Redis eviction policy does catalog-service use?", [(CACHE, "Eviction behaviour")], ["allkeys-lru"], "lexical"),
    ("What is the bcrypt cost factor used by auth-service?", [(AR, "Login latency spikes")], ["12"], "lexical"),
    ("What should --max-old-space-size be used for?", [(MEM, "Node.js services")], ["heap limit"], "lexical"),
    # ---- semantic: paraphrased symptoms
    ("Customers are logged out and every API call is rejected right after we changed the token signing keys. Why?", [(AR, "Token validation errors"), (I22, "Root cause")], ["cache"], "semantic"),
    ("Password reset emails are arriving hours late. What could be going on?", [(I27, "Root cause"), (NR, "Queue backlog")], ["shared one queue"], "semantic"),
    ("Product search is failing for some users and the cluster status is red. What usually causes this?", [(SR, "Cluster health yellow or red"), (I34, "Root cause")], ["disk"], "semantic"),
    ("Checkout became slow after the latest orders release. What changed?", [(DN43, "Changes"), (I31, "Root cause")], ["pool"], "semantic"),
    ("Card payments started timing out during the evening rush after a deploy. What happened last time?", [(I18, "Root cause")], ["3 seconds"], "semantic"),
    ("A background job keeps getting killed by the platform even though the Java heap is not full. Why?", [(MEM, "Container killed by the kernel")], ["native memory"], "semantic"),
    ("How do I safely change a database column without downtime?", [(DEP, "Database migrations")], ["expand-and-contract"], "semantic"),
    ("How does a new release get tested on a small slice of production traffic?", [(DEP, "Canary releases")], ["10 percent"], "semantic"),
    ("When does the pipeline automatically undo a bad release?", [(DEP, "Canary releases")], ["2 percent"], "semantic"),
    ("Signing in has become slow; what is the usual reason?", [(AR, "Login latency spikes")], ["CPU saturation"], "semantic"),
    ("Two orders for the same items keep failing with database lock errors. Why?", [(IR, "Stock reservation deadlocks")], ["different order"], "semantic"),
    ("Users get 'Payment could not be processed' at checkout. Where should I look first?", [(PR, "Card authorization failures")], ["gateway status page"], "semantic"),
    ("The email worker restarts endlessly right after start-up. What is a likely cause?", [(I44, "Root cause"), (NR, "Required configuration")], ["environment variable"], "semantic"),
    ("Why must we never wipe the Redis database used by the payment service?", [(PR, "Idempotency key conflicts")], ["double charges"], "semantic"),
    ("The load balancer says there are no healthy targets. Which error code is that?", [(HTTP, "503 Service Unavailable")], ["503"], "semantic"),
    ("Requests are cut off by the load balancer because the backend answers too slowly. What status do clients see?", [(HTTP, "504 Gateway Timeout")], ["504"], "semantic"),
    ("Connections get dropped by the load balancer with an invalid response; what setting mismatch can cause that?", [(HTTP, "502 Bad Gateway")], ["keep-alive"], "semantic"),
    ("How long do JWT access tokens live?", [(AA, "Overview")], ["15 minute"], "semantic"),
    ("Where are user passwords stored?", [(AA, "Storage")], ["auth-db"], "semantic"),
    ("Which team should I page for the payment service?", [(PR, "Payments API Runbook"), (PLAT, "Services and owners")], ["Payments team"], "semantic"),
    ("What is the latency target for the orders service?", [(PLAT, "Service level objectives")], ["300 ms"], "semantic"),
    ("Do we store full card numbers?", [(PA, "Data retention")], ["never stored"], "semantic"),
    ("How long are payment ledger records kept?", [(PA, "Data retention")], ["7 years"], "semantic"),
    ("How are calls to the card processor retried?", [(PA, "Timeouts and retries")], ["2 retries"], "semantic"),
    ("What happens when a user enters the wrong password too many times?", [(AR, "Account lockout")], ["15 minutes"], "semantic"),
    ("How often are signing keys replaced?", [(AR, "Signing key rotation")], ["30 days"], "semantic"),
    ("Search queries are very slow; what pattern should we block?", [(SR, "Slow queries")], ["leading"], "semantic"),
    ("Event processing for stock updates is falling behind; is Kafka usually to blame?", [(IR, "Consumer lag on inventory-events")], ["slow database"], "semantic"),
    ("When does the stock comparison with the warehouse run?", [(IR, "Nightly reconciliation job")], ["02:00 UTC"], "semantic"),
    ("Why did the nightly inventory job run out of memory?", [(I40, "Root cause")], ["full product catalog"], "semantic"),
    ("Our service pauses for seconds at a time and requests time out; what JVM issue could it be?", [(MEM, "Long garbage collection pauses")], ["GC pauses"], "semantic"),
    ("How do read replicas behave during big batch writes?", [(DB, "Replica lag")], ["lag"], "semantic"),
    ("What does the checkout request path look like across services?", [(PLAT, "Request flow for checkout")], ["inventory-service"], "semantic"),
    ("How long are application logs kept?", [(OBS, "Logs")], ["30 days"], "semantic"),
    ("What alarms does every service have by default?", [(OBS, "Alarms")], ["p95-latency"], "semantic"),
    ("What happens to the catalog database when the cache hit ratio drops?", [(CACHE, "Eviction behaviour")], ["increases load"], "semantic"),
    ("How do we stop many requests from rebuilding the same expired cache entry?", [(CACHE, "Cache stampede protection")], ["request coalescing"], "semantic"),
    ("How do I undo a deployment by hand?", [(DEP, "Manual rollback"), (OR, "Rollback procedure")], ["previous task definition"], "semantic"),
    ("Do config-only changes skip the canary?", [(DEP, "Configuration changes")], ["still go through the canary"], "semantic"),
    ("What risk was noted for the orders 4.3 release?", [(DN43, "Known risks")], ["not been load tested"], "semantic"),
    ("What changed in payments release 2.8?", [(DN28, "Changes")], ["3 seconds"], "semantic"),
    ("How was the search outage fixed?", [(I34, "Resolution")], ["deleted"], "semantic"),
    ("What follow-ups came out of the delayed password reset emails?", [(I27, "Follow-up actions")], ["separate high-priority queue"], "semantic"),
    ("What is the email sending rate limit?", [(NR, "Email provider throttling"), (I27, "Root cause")], ["14 messages per second"], "semantic"),
    # ---- multi-hop: two sections needed
    ("orders-api uses 200 database connections out of the cluster; how does pool size relate to that budget?", [(DB, "Connection limits"), (PLAT, "Shared database cluster")], ["task count"], "multi"),
    ("The payments gateway p99 is 4.5 seconds; was the 2.8 timeout safe, and what is the default timeout?", [(I18, "Root cause"), (PA, "Timeouts and retries")], ["8 second"], "multi"),
    ("After key rotation, how long should we wait before signing with a new key and why?", [(AR, "Signing key rotation"), (AR, "Token validation errors")], ["2 hours"], "multi"),
    ("What -Xmx should a 2 GB job use, and what went wrong in the inventory OOM incident?", [(MEM, "Container killed by the kernel"), (I40, "Root cause")], ["75 percent"], "multi"),
    ("A search data node is at 96 percent disk; what will happen and what alert threshold was added afterwards?", [(SR, "Cluster health yellow or red"), (I34, "Follow-up actions")], ["80 percent"], "multi"),
    ("Which required notification settings exist and which one caused the October crash?", [(NR, "Required configuration"), (I44, "Root cause")], ["SMTP_FROM_ADDRESS"], "multi"),
    ("What rollback steps does the orders runbook give, and does a rollback go through the canary?", [(OR, "Rollback procedure"), (DEP, "Manual rollback")], ["skip the canary"], "multi"),
    ("How do I find the logs and metrics for orders-api?", [(OBS, "Logs"), (OBS, "Metrics")], ["/ecs/orders-api"], "multi"),
    # ---- unanswerable
    ("What is the on-call phone number for the Payments team?", [], [], "unanswerable"),
    ("How do I rotate the TLS certificate on the load balancer?", [], [], "unanswerable"),
    ("What Kubernetes version does the platform run?", [], [], "unanswerable"),
    ("What is the monthly AWS bill for search-api?", [], [], "unanswerable"),
    ("How do I configure Datadog APM for orders-api?", [], [], "unanswerable"),
    ("Who approved the payments 2.8 release?", [], [], "unanswerable"),
    ("What is the GraphQL schema for the catalog?", [], [], "unanswerable"),
    ("How many users signed up last month?", [], [], "unanswerable"),
    ("What is the disaster recovery RTO for auth-db?", [], [], "unanswerable"),
    ("What mobile app versions are still supported?", [], [], "unanswerable"),
    ("How is the Redis cluster for idempotency keys backed up?", [], [], "unanswerable"),
    ("What CDN provider serves static assets?", [], [], "unanswerable"),
    ("What is the password policy minimum length?", [], [], "unanswerable"),
    ("How do I request access to production databases?", [], [], "unanswerable"),
    ("What is the SLA for the warehouse system integration?", [], [], "unanswerable"),
    ("What was the root cause of INC-2026-050?", [], [], "unanswerable"),
    ("Which region is the disaster recovery site in?", [], [], "unanswerable"),
    ("How do I run the orders-api test suite locally?", [], [], "unanswerable"),
    ("What is the cost of the SES sending limit increase?", [], [], "unanswerable"),
    ("What on-call compensation do engineers receive?", [], [], "unanswerable"),
]


def main() -> None:
    out = Path(__file__).with_name("questions.jsonl")
    with out.open("w") as f:
        for i, (q, rel, facts, kind) in enumerate(Q, start=1):
            f.write(json.dumps({
                "id": f"q{i:03d}",
                "question": q,
                "relevant": [{"document": d, "section": s} for d, s in rel],
                "answerable": bool(rel),
                "expected_facts": facts,
                "kind": kind,
                "split": "tune" if i % 10 in (1, 4, 7) else "test",
            }) + "\n")
    print(f"wrote {len(Q)} questions to {out}")


if __name__ == "__main__":
    main()
