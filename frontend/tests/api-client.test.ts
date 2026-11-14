import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, request, session } from "@/lib/api/client"

const json = (status: number, body: unknown) =>
  new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })

describe("request()", () => {
  const fetchMock = vi.fn()
  beforeEach(async () => {
    // The client releases its in-flight refresh on the next tick; let the previous test's settle.
    await new Promise((r) => setTimeout(r, 5))
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    session.setToken("old-token")
    session.setWorkspaceId("ws-1")
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    session.onUnauthorized(null)
  })

  it("sends the bearer token, workspace header and cookies", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ok: true }))
    await request("/documents")
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toMatch(/\/documents$/)
    expect(init.credentials).toBe("include")
    expect(init.headers.Authorization).toBe("Bearer old-token")
    expect(init.headers["X-Workspace-Id"]).toBe("ws-1")
  })

  it("refreshes once on 401 and retries with the new token", async () => {
    fetchMock
      .mockResolvedValueOnce(json(401, { error: { code: "unauthorized", message: "expired" } }))
      .mockResolvedValueOnce(json(200, { access_token: "new-token", user: { id: "u", email: "e@x.dev", display_name: "E" } }))
      .mockResolvedValueOnce(json(200, { items: [] }))
    const res = await request<{ items: unknown[] }>("/documents")
    expect(res.items).toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/auth\/refresh$/)
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer new-token")
  })

  it("shares one refresh between concurrent 401s (single-flight)", async () => {
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (String(url).endsWith("/auth/refresh")) {
        await new Promise((r) => setTimeout(r, 10))
        return json(200, { access_token: "new-token", user: { id: "u", email: "e@x.dev", display_name: "E" } })
      }
      const auth = (init.headers as Record<string, string>).Authorization
      return auth === "Bearer new-token" ? json(200, { ok: true }) : json(401, { error: { code: "unauthorized", message: "x" } })
    })
    await Promise.all([request("/a"), request("/b"), request("/c")])
    const refreshes = fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/auth/refresh"))
    expect(refreshes).toHaveLength(1)
  })

  it("signs the user out when the refresh also fails", async () => {
    const onUnauthorized = vi.fn()
    session.onUnauthorized(onUnauthorized)
    fetchMock.mockResolvedValueOnce(json(401, { error: { code: "unauthorized", message: "x" } })).mockResolvedValueOnce(json(401, { error: { code: "unauthorized", message: "x" } }))
    await expect(request("/documents")).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledOnce()
    expect(session.getToken()).toBeNull()
  })

  it("turns the backend error envelope into an ApiError", async () => {
    fetchMock.mockResolvedValueOnce(json(422, { error: { code: "validation_error", message: "Bad input", details: { field: "email" } } }))
    const err = await request("/x", { noRetry: true }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(422)
    expect(err.code).toBe("validation_error")
    expect(err.message).toBe("Bad input")
  })

  it("reports a network failure as a readable error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"))
    const err = await request("/x").catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.code).toBe("network_error")
  })
})
