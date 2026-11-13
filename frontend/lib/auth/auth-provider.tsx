"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { api } from "@/lib/api"
import { session } from "@/lib/api/client"
import type { AuthResponse, User, Workspace } from "@/lib/types/api"

const WS_KEY = "opspilot_active_workspace" // non-sensitive convenience only

type Status = "loading" | "authenticated" | "anonymous"

interface AuthContextValue {
  status: Status
  user: User | null
  workspaces: Workspace[]
  workspace: Workspace | null
  login(email: string, password: string): Promise<void>
  register(email: string, password: string, display_name: string): Promise<void>
  logout(): Promise<void>
  switchWorkspace(id: string): void
  createWorkspace(name: string): Promise<Workspace>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function readStoredWorkspace(): string | null {
  try {
    return localStorage.getItem(WS_KEY)
  } catch {
    return null
  }
}

function storeWorkspace(id: string) {
  try {
    localStorage.setItem(WS_KEY, id)
  } catch {
    /* storage unavailable — fine */
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter()
  const queryClient = useQueryClient()
  const [status, setStatus] = useState<Status>("loading")
  const [user, setUser] = useState<User | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspace, setWorkspace] = useState<Workspace | null>(null)

  const selectWorkspace = useCallback((list: Workspace[], preferred: string | null) => {
    const ws = list.find((w) => w.id === preferred) ?? list[0] ?? null
    session.setWorkspaceId(ws?.id ?? null)
    if (ws) storeWorkspace(ws.id)
    setWorkspace(ws)
  }, [])

  const loadSession = useCallback(
    async (me?: User) => {
      const [u, list] = await Promise.all([me ? Promise.resolve(me) : api.auth.me(), api.workspaces.list()])
      setUser(u)
      setWorkspaces(list)
      selectWorkspace(list, readStoredWorkspace())
      setStatus("authenticated")
    },
    [selectWorkspace],
  )

  const reset = useCallback(() => {
    session.setToken(null)
    session.setWorkspaceId(null)
    setUser(null)
    setWorkspaces([])
    setWorkspace(null)
    setStatus("anonymous")
    queryClient.clear()
  }, [queryClient])

  // On first load, try to restore the session from the refresh cookie.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const ok = await api.auth.refresh()
        if (cancelled) return
        if (ok) await loadSession()
        else setStatus("anonymous")
      } catch {
        if (!cancelled) setStatus("anonymous")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadSession])

  useEffect(() => {
    session.onUnauthorized(() => {
      reset()
      router.replace("/login")
    })
    return () => session.onUnauthorized(null)
  }, [reset, router])

  const handleAuth = useCallback(
    async (res: AuthResponse) => {
      session.setToken(res.access_token)
      await loadSession(res.user)
    },
    [loadSession],
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      workspaces,
      workspace,
      login: async (email, password) => handleAuth(await api.auth.login({ email, password })),
      register: async (email, password, display_name) => handleAuth(await api.auth.register({ email, password, display_name })),
      logout: async () => {
        try {
          await api.auth.logout()
        } finally {
          reset()
          router.replace("/login")
        }
      },
      switchWorkspace: (id) => selectWorkspace(workspaces, id),
      createWorkspace: async (name) => {
        const ws = await api.workspaces.create({ name })
        const list = [...workspaces, ws]
        setWorkspaces(list)
        selectWorkspace(list, ws.id)
        return ws
      },
    }),
    [status, user, workspaces, workspace, handleAuth, reset, router, selectWorkspace],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>")
  return ctx
}

export function useWorkspaceId(): string | null {
  return useAuth().workspace?.id ?? null
}
