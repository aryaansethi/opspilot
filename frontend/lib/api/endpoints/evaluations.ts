"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
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
  return useQuery({ queryKey: qk.evalRun(ws, id), queryFn: () => api.evaluations.get(id), enabled: !!ws })
}

export function useRunEvaluation() {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return useMutation({
    mutationFn: (input: { dataset_version?: string; config_label?: string }) => api.evaluations.run(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.evalRuns(ws) }),
  })
}
