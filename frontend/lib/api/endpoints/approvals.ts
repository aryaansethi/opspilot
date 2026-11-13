"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { ApprovalRequest } from "@/lib/types/api"
import { qk } from "./keys"

export function usePendingApprovals() {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.pendingApprovals(ws), queryFn: () => api.approvals.pending(), enabled: !!ws })
}

function useDecide(fn: (id: string) => Promise<ApprovalRequest>) {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return useMutation({
    mutationFn: fn,
    onSuccess: (apr) => {
      qc.invalidateQueries({ queryKey: qk.investigationPart(ws, apr.investigation_id, "approvals") })
      qc.invalidateQueries({ queryKey: qk.pendingApprovals(ws) })
    },
  })
}

export const useApprove = () => useDecide((id) => api.approvals.approve(id))
export const useReject = () => useDecide((id) => api.approvals.reject(id))
