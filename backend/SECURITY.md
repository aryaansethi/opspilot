# Backend security review

Scope: the FastAPI backend, worker and MCP servers in `backend/`, reviewed against the project's
security requirements. Every fix below has a regression test (file in brackets). The system is
local-first, and no cloud resources were provisioned for this review.

## Fixed in this review

| Area | Finding | Fix |
|---|---|---|
| Authentication | Access tokens had no issuer or audience, so a token minted elsewhere with the same secret would be accepted | Tokens carry `iss`/`aud`; `exp`, `iat`, `sub`, `iss` and `aud` are required, and `alg: none` is rejected (`test_security.py`) |
| Rate limiting | Only login/register were limited; `/ask` and investigations each start long LLM work | Per-user limits on `/ask` (30/min), investigations (10/min) and evaluation runs (30/h); configurable (`test_security.py`) |
| Resource exhaustion | Each live event stream holds a database connection, with no cap | At most 5 concurrent streams per user; 429 beyond that (`test_security.py`) |
| Audit / detection | Failed logins were not recorded anywhere | `auth.login_failed` log with client IP and a truncated SHA-256 of the email; never the password (`test_security.py`) |
| Prompt injection | Evidence escaping only handled the exact string `</evidence>`, and titles were placed in attributes unescaped | Tags are neutralised in any case or spacing, and attributes are fully escaped; measured with injected documents and logs (`test_prompt_injection.py`, `make eval-extra`) |
| Integration errors | Upstream failures surfaced as a generic "Error executing tool" | Clear, non-leaking messages for denied permissions, throttling, missing credentials, timeouts and invalid responses (`test_mcp_failures.py`) |
| HTTP headers | No basic hardening headers | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; `Cache-Control: no-store` on auth routes (`test_security.py`) |
| Job integrity | Duplicate queue deliveries could run a job twice; dead workers left jobs "running" | Atomic claims and a reaper (`test_jobs.py`) |

## Verified, no change needed

- **Workspace isolation:** every tenant route depends on a membership check for `X-Workspace-Id`, and
  queries filter by `workspace_id`. Other workspaces get 403/404 (`test_security.py`,
  `test_documents.py`, `test_investigations.py`).
- **Passwords:** Argon2id with length limits of 10–128 characters (the upper bound prevents hashing
  DoS). Login timing does not reveal whether an email exists.
- **Refresh tokens:** opaque, stored hashed, rotated on every use. Reuse revokes all sessions. The
  cookie is `HttpOnly`, `SameSite=Lax`, scoped to `/api/v1/auth`, and `Secure` is enforced in production.
- **Secrets:** production refuses to start with the development JWT secret. The GitHub token is
  readable only by the GitHub MCP process (and only its container in Compose). Tool arguments are
  redacted before auditing, and log processors redact secret-like keys.
- **Least privilege:** MCP tools are server-side allowlisted (registry + catalog). The LLM picks task
  types, never tool names or arguments, and every argument is schema-validated and checked against
  the workspace allowlists. Write tools require an approved action. Terraform task roles are
  read-only where possible.
- **Input validation:** Pydantic models bound every field. Uploads are checked by extension, MIME
  type, magic bytes and size, and filenames cannot contain path separators.
- **Audit:** document, integration, investigation and approval actions write `audit_events`, and
  every tool call writes `tool_invocations`.

## Accepted risks (documented, not fixed)

- **Access tokens stay valid until expiry after logout** (at most 15 minutes). Refresh tokens are
  revoked immediately.
- **In-memory rate limits and stream caps are per process.** With several API replicas a shared
  store would be needed.
- **Evaluation runs are global, not per workspace.** They use only the synthetic dataset, and
  starting one requires the owner role.
- **The requester can approve their own write action.** A separate approver (four-eyes) would be a
  policy option, but there is no write integration (Jira) yet.
- **A local LLM can still be persuaded to say things.** The defences limit the impact (no tool
  execution from model text; citation and number validation), and the remaining rate is measured
  by the injection evaluation rather than assumed to be zero.
