"use client"

import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { SearchFilters, SearchRequest } from "@/lib/types/api"

export function useSearch() {
  return useMutation({
    mutationFn: ({ debug, ...input }: SearchRequest & { debug: boolean }) =>
      debug ? api.search.debug(input) : api.search.search(input),
  })
}

export function useAsk() {
  return useMutation({
    mutationFn: (input: { question: string; filters?: SearchFilters }) => api.search.ask(input),
  })
}
