# OpsPilot AI — Frontend

Next.js 15 (App Router) client for OpsPilot AI. All business logic lives in the FastAPI backend — this app only renders it.
See `../ARCHITECTURE.md` §3 for the design and `../V0_FRONTEND_PROMPT.md` for the full screen spec.

## Quick start

```bash
npm install
cp .env.example .env.local   # then edit
npm run dev                  # http://localhost:3000
```

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
- Evaluation numbers are invented placeholders for layout only — never quote them.

Components never import mock data directly; they only use the hooks in `lib/api/endpoints/`.

## How the client talks to the API

- **Auth**: the access token is kept **in memory only**. The refresh token is an httpOnly cookie set by the API, so every request uses `credentials: "include"`. On a 401 the client calls `POST /auth/refresh` once (single-flight) and retries; if that fails the user is sent to `/login`.
- **Tenant scope**: every request sends `X-Workspace-Id` for the active workspace. The backend enforces isolation; query keys are prefixed with the workspace ID so switching never shows another workspace's cached data.
- **Errors**: `{ "error": { code, message, details } }` responses become `ApiError` (`lib/api/client.ts`).
- **Live progress**: `lib/sse.ts` reads `GET /investigations/{id}/events` with `fetch` + `ReadableStream` (EventSource can't send `Authorization`), reconnects with `Last-Event-ID`, and invalidates the related TanStack Query caches on each event.

### Endpoints the frontend uses beyond ARCHITECTURE.md §6

The backend needs these too:

| Endpoint | Used by |
|---|---|
| `GET /documents/{id}/chunks` → `DocumentChunk[]` | Document detail page |
| `GET /approvals?status=pending` → `ApprovalRequest[]` | Dashboard + sidebar pending count |
| `PATCH /integrations/{id}/tools/{tool}` `{ enabled }` → `Integration` | Tool enable toggles |

And two optional fields on `Investigation`: `missing_parameters` (already in the spec) and `failed_steps: string[]` (shown in the PARTIAL banner).

When the backend publishes OpenAPI, replace `lib/types/api.ts` with `openapi-typescript` output.

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
```

## Deploying to Vercel

Set the project root to `frontend/`, add `NEXT_PUBLIC_API_BASE_URL` (and leave `NEXT_PUBLIC_API_MODE` unset or `real`). Use a custom domain on the same site as the API (`app.<domain>` / `api.<domain>`) so the refresh cookie isn't third-party — see ARCHITECTURE.md "Cross-domain auth note".
