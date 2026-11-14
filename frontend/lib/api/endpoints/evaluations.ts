"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { RunEvaluationRequest } from "@/lib/types/api"
import { qk } from "./keys"

export function useEvaluationRuns() {
  const ws = useWorkspaceId()
  return useQuery({
    queryKey: qk.evalRuns(ws),
    queryFn: () => api.evaluations.runs(),
    enabled: !!ws,
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "running") ? 3000 : false),
  })
}

export function useEvaluationRun(id: string) {
  const ws = useWorkspaceId()
  return useQuery({
    queryKey: qk.evalRun(ws, id),
    queryFn: () => api.evaluations.get(id),
    enabled: !!ws,
    // Answers runs take ~1 min per question; keep per-question results flowing in.
    refetchInterval: (q) => (q.state.data?.status === "running" ? 5000 : false),
  })
}

export function useEvaluationCapabilities() {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: ["ws", ws, "evaluations", "capabilities"], queryFn: () => api.evaluations.capabilities(), enabled: !!ws, staleTime: 5 * 60_000 })
}

export function useRunEvaluation() {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return useMutation({
    mutationFn: (input: RunEvaluationRequest) => api.evaluations.run(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.evalRuns(ws) }),
  })
}
