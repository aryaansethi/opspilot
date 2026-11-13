"use client"

import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { FeedbackRequest } from "@/lib/types/api"

export function useSendFeedback() {
  return useMutation({ mutationFn: (input: FeedbackRequest) => api.feedback.send(input) })
}
