"use client"

import { useInfiniteQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { AuditFilters } from "@/lib/types/api"
import { qk } from "./keys"

export function useAuditEvents(filters: Omit<AuditFilters, "cursor">) {
  const ws = useWorkspaceId()
  return useInfiniteQuery({
    queryKey: qk.audit(ws, filters),
    queryFn: ({ pageParam }) => api.audit.list({ ...filters, cursor: pageParam ?? undefined }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
    enabled: !!ws,
  })
}
