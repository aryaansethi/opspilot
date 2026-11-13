"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { CreateIntegrationRequest } from "@/lib/types/api"
import { qk } from "./keys"

export function useIntegrations() {
  const ws = useWorkspaceId()
  return useQuery({ queryKey: qk.integrations(ws), queryFn: () => api.integrations.list(), enabled: !!ws })
}

function useInvalidate() {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  return () => qc.invalidateQueries({ queryKey: qk.integrations(ws) })
}

export function useCreateIntegration() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (input: CreateIntegrationRequest) => api.integrations.create(input), onSuccess: invalidate })
}

export function useRemoveIntegration() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.integrations.remove(id), onSuccess: invalidate })
}

export function useTestIntegration() {
  const invalidate = useInvalidate()
  return useMutation({ mutationFn: (id: string) => api.integrations.test(id), onSuccess: invalidate })
}

export function useSetToolEnabled() {
  const invalidate = useInvalidate()
  return useMutation({
    mutationFn: (v: { id: string; tool: string; enabled: boolean }) => api.integrations.setToolEnabled(v.id, v.tool, v.enabled),
    onSuccess: invalidate,
  })
}
