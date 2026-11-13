"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { ActionRequest, ContinueInvestigationRequest, CreateInvestigationRequest } from "@/lib/types/api"
import type { InvestigationListParams } from "../contract"
import { qk } from "./keys"

export function useInvestigations(params?: InvestigationListParams) {
  const ws = useWorkspaceId()
  return useQuery({
    queryKey: qk.investigations(ws, params),
    queryFn: () => api.investigations.list(params),
    enabled: !!ws,
  })
}

export function useInvestigation(id: string) {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.investigation(ws, id), queryFn: () => api.investigations.get(id), enabled: !!ws })
}

export function useEvidence(id: string) {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.investigationPart(ws, id, "evidence"), queryFn: () => api.investigations.evidence(id), enabled: !!ws })
}

export function useHypotheses(id: string) {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.investigationPart(ws, id, "hypotheses"), queryFn: () => api.investigations.hypotheses(id), enabled: !!ws })
}

export function useToolCalls(id: string) {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.investigationPart(ws, id, "tool-calls"), queryFn: () => api.investigations.toolCalls(id), enabled: !!ws })
}

export function useInvestigationApprovals(id: string) {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.investigationPart(ws, id, "approvals"), queryFn: () => api.investigations.approvals(id), enabled: !!ws })
}

export function useReport(id: string) {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.investigationPart(ws, id, "report"), queryFn: () => api.investigations.report(id), enabled: !!ws })
}

export function useCreateInvestigation() {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return useMutation({
    mutationFn: (input: CreateInvestigationRequest) => api.investigations.create(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ws", ws, "investigations"] }),
  })
}

export function useContinueInvestigation(id: string) {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return useMutation({
    mutationFn: (input: ContinueInvestigationRequest) => api.investigations.continue(id, input),
    onSuccess: (inv) => qc.setQueryData(qk.investigation(ws, id), inv),
  })
}

export function useRequestAction(id: string) {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return useMutation({
    mutationFn: (input: ActionRequest) => api.investigations.requestAction(id, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk.investigationPart(ws, id, "approvals") })
      qc.invalidateQueries({ queryKey: qk.pendingApprovals(ws) })
    },
  })
}
