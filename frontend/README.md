# OpsPilot AI — Frontend

Next.js 15 (App Router) client for OpsPilot AI. All business logic lives in the FastAPI backend — this app only renders it.
See `../ARCHITECTURE.md` §3 for the design and `../V0_FRONTEND_PROMPT.md` for the original screen spec.

**Status:** every screen runs against the real backend (auth, knowledge base, search and Ask, investigations with live events, approvals, integrations, audit log, evaluations). Mock mode remains for previews without a backend.

## Quick start

```bash
npm install
cp .env.example .env.local   # defaults to the real backend at http://localhost:8000/api/v1
npm run dev                  # http://localhost:3000
```

Start the backend first (see `../README.md`). Use port 3000: the backend's CORS and the LocalStack bucket CORS allow `http://localhost:3000`.

| Script | What it does |
|---|---|
| `npm run dev` | Dev server (Turbopack) |
| `npm run build` | Production build |
| `npm run lint` | ESLint |
| `npx tsc --noEmit` | Type check |

## Mock mode vs real mode

The app talks to the backend through one typed contract (`lib/api/contract.ts`) with two implementations:

| Mode | Env | Implementation | Use it for |
|---|---|---|---|
| **real** (default) | `NEXT_PUBLIC_API_MODE=real` | `lib/api/http.ts` → `NEXT_PUBLIC_API_BASE_URL` | Development against the backend, production |
| **mock** | `NEXT_PUBLIC_API_MODE=mock` | `lib/api/mock/` (in-memory sample data) | UI previews and demos without a backend |

In mock mode:
- A yellow banner on every screen says the data is sample data.
- Any email + a password of 8+ characters signs you in (pre-filled on the login page).
- New investigations run through the full state machine on timers, streaming simulated events. Leave out the service or time range to see the "needs input" step.
- Uploads go through the 3-step flow (upload URL → PUT → complete) and finish indexing after ~5 s.
- Evaluation numbers are invented placeholders for layout only — never quote them. Real numbers come from `POST /evaluations/run` on the backend.

Components never import mock data directly; they only use the hooks in `lib/api/endpoints/`.

## How the client talks to the API

- **Auth**: the access token is kept **in memory only**. The refresh token is an httpOnly cookie set by the API, so every request uses `credentials: "include"`. On a 401 the client calls `POST /auth/refresh` once (single-flight) and retries; if that fails the user is sent to `/login`.
- **Tenant scope**: every request sends `X-Workspace-Id` for the active workspace. The backend enforces isolation; query keys are prefixed with the workspace ID so switching never shows another workspace's cached data.
- **Errors**: `{ "error": { code, message, details } }` responses become `ApiError` (`lib/api/client.ts`).
- **Live progress**: `lib/sse.ts` reads `GET /investigations/{id}/events` with `fetch` + `ReadableStream` (EventSource can't send `Authorization`), reconnects with `Last-Event-ID`, and invalidates the related TanStack Query caches on each event.

### Adapting to the backend

`lib/api/http.ts` is the only place that knows backend wire details. It currently:

- maps chunk `content` → `excerpt` for the document detail page;
- sends search/ask filters as lists (`source_types`, `services`, `environments`);
- returns `null` for `GET /investigations/{id}/report` while it is 404 (report not ready yet).

Other things worth knowing:

- Optional fields arrive as `null`, so UI checks use `!= null`, not `!== undefined`.
- The event stream sends `state_changed {from, to}`; only `tool_call_completed` carries `invocation_id`, so the timeline pairs each `tool_call_started` with the next completion of the same tool.
- Evidence uses backend labels (`E1`, `E2`, …), which match the citations in the report markdown.
- Investigations finish as `COMPLETED` / `PARTIAL` / `FAILED_*`; approvals can end `failed` with an `error` (shown as-is).
- Evaluation runs are global (synthetic dataset), with `kind` = `retrieval` | `answers` and `split` = `test` | `tune` | `all`. Faithfulness isn't measured, so it isn't shown.

When the backend's OpenAPI types settle, `lib/types/api.ts` can be generated with `openapi-typescript`.

## Docker

`Dockerfile` builds a small standalone server (`output: "standalone"` in `next.config.ts`). Because
`NEXT_PUBLIC_*` values are inlined at build time, the API URL is a build argument, and it's the URL the
**browser** calls (the host-published API port), not a Compose service name:

```bash
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=http://localhost:8080/api/v1 -t opspilot-frontend .
```

`docker compose --profile app up` (repository root) builds and runs it on port 3000 next to the API on 8080.

## CI

`.github/workflows/frontend.yml` runs `npm ci`, `tsc --noEmit`, `npm run lint` and `npm run build` on pushes and pull requests that touch `frontend/`.

## Layout

```
app/(marketing)   landing
app/(auth)        login, register
app/(app)         authenticated shell: dashboard, investigations, search, knowledge, integrations, evaluations, audit
components/ui     shadcn/ui primitives
components/*      common, layout, investigation, knowledge
lib/api           client, contract, http + mock implementations, TanStack Query hooks
lib/auth          AuthProvider (session, workspaces)
lib/sse.ts        investigation event stream
lib/evaluations.ts  strategy names and answer-metric labels shared by the evaluation pages
```

## Deploying to Vercel

Set the project root to `frontend/`, add `NEXT_PUBLIC_API_BASE_URL` (and leave `NEXT_PUBLIC_API_MODE` unset or `real`). Use a custom domain on the same site as the API (`app.<domain>` / `api.<domain>`) so the refresh cookie isn't third-party — see ARCHITECTURE.md "Cross-domain auth note".
