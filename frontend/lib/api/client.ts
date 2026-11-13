import { API_BASE_URL } from "./config"
import type { ApiErrorBody, AuthResponse } from "@/lib/types/api"

/** Normalised error for every failed API call. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details?: Record<string, unknown>

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.code = code
    this.details = details
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return "Something went wrong"
}

// ---- Session state (memory only; the refresh token lives in an httpOnly cookie set by the API) ----

let accessToken: string | null = null
let workspaceId: string | null = null
let unauthorizedHandler: (() => void) | null = null

export const session = {
  getToken: () => accessToken,
  setToken: (token: string | null) => {
    accessToken = token
  },
  getWorkspaceId: () => workspaceId,
  setWorkspaceId: (id: string | null) => {
    workspaceId = id
  },
  /** Called when a request is still 401 after one refresh attempt. */
  onUnauthorized: (handler: (() => void) | null) => {
    unauthorizedHandler = handler
  },
}

export function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  if (workspaceId) headers["X-Workspace-Id"] = workspaceId
  return headers
}

async function toApiError(res: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> | null = null
  try {
    body = (await res.json()) as Partial<ApiErrorBody>
  } catch {
    body = null
  }
  const e = body?.error
  return new ApiError(res.status, e?.code ?? `http_${res.status}`, e?.message ?? res.statusText ?? "Request failed", e?.details)
}

// Single-flight refresh so parallel 401s trigger only one /auth/refresh call.
let refreshInFlight: Promise<boolean> | null = null

export function refreshAccessToken(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/auth/refresh`, { method: "POST", credentials: "include" })
        if (!res.ok) return false
        const data = (await res.json()) as AuthResponse
        accessToken = data.access_token
        return true
      } catch {
        return false
      } finally {
        setTimeout(() => {
          refreshInFlight = null
        }, 0)
      }
    })()
  }
  return refreshInFlight
}

type Query = Record<string, string | number | boolean | undefined | null>

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
  body?: unknown
  query?: Query
  signal?: AbortSignal
  /** Skip the refresh-and-retry dance (used by auth endpoints). */
  noRetry?: boolean
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`${API_BASE_URL}${path}`)
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v))
    }
  }
  return url.toString()
}

export async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const doFetch = () =>
    fetch(buildUrl(path, opts.query), {
      method: opts.method ?? "GET",
      credentials: "include",
      signal: opts.signal,
      headers: {
        Accept: "application/json",
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...authHeaders(),
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    })

  let res: Response
  try {
    res = await doFetch()
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err
    throw new ApiError(0, "network_error", "Can't reach the OpsPilot API. Check that the backend is running.")
  }

  if (res.status === 401 && !opts.noRetry) {
    const refreshed = await refreshAccessToken()
    if (refreshed) res = await doFetch()
    if (res.status === 401) {
      accessToken = null
      unauthorizedHandler?.()
    }
  }

  if (!res.ok) throw await toApiError(res)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

/** PUT a file straight to a presigned S3 URL with progress reporting. */
export function uploadToPresignedUrl(
  url: string,
  headers: Record<string, string>,
  file: File,
  onProgress: (pct: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", url)
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new ApiError(xhr.status, "upload_failed", "Upload to storage failed"))
    xhr.onerror = () => reject(new ApiError(0, "upload_failed", "Upload to storage failed"))
    xhr.send(file)
  })
}
