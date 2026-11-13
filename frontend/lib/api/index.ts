import { IS_MOCK } from "./config"
import type { ApiContract } from "./contract"
import { httpApi } from "./http"
import { mockApi } from "./mock"

/** The active API implementation. Components use the hooks in ./endpoints, never this directly. */
export const api: ApiContract = IS_MOCK ? mockApi : httpApi

export { ApiError, errorMessage } from "./client"
