export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "")

/** "mock" serves sample data from lib/api/mock — for previews only. Anything else talks to the real backend. */
export const API_MODE: "mock" | "real" = process.env.NEXT_PUBLIC_API_MODE === "mock" ? "mock" : "real"

export const IS_MOCK = API_MODE === "mock"
