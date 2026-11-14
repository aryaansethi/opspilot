"use client"

import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import { authHeaders, refreshAccessToken } from "@/lib/api/client"
import { API_BASE_URL, IS_MOCK } from "@/lib/api/config"
import { qk } from "@/lib/api/endpoints/keys"
import { useWorkspaceId } from "@/lib/auth/auth-provider"
import type { InvestigationEvent, InvestigationEventType } from "@/lib/types/api"

export type StreamStatus = "connecting" | "open" | "reconnecting" | "closed" | "replayed"

/** live: follow new events; replay: fetch the history once and close (finished investigations). */
export type StreamMode = "live" | "replay"

const PART_FOR_EVENT: Partial<Record<InvestigationEventType, string[]>> = {
  tool_call_started: ["tool-calls"],
  tool_call_completed: ["tool-calls"],
  evidence_added: ["evidence"],
  hypothesis_added: ["hypotheses"],
  report_ready: ["report"],
  approval_requested: ["approvals"],
}

/** Parse one SSE frame ("id: …\nevent: …\ndata: …"). Returns null for comments/heartbeats. */
export function parseSseFrame(frame: string): InvestigationEvent | null {
  let id: string | undefined
  let type: string | undefined
  const data: string[] = []
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue
    const idx = line.indexOf(":")
    const field = idx === -1 ? line : line.slice(0, idx)
    const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "")
    if (field === "id") id = value
    else if (field === "event") type = value
    else if (field === "data") data.push(value)
  }
  if (!data.length) return null
  try {
    const parsed = JSON.parse(data.join("\n")) as Partial<InvestigationEvent>
    return {
      seq: parsed.seq ?? Number(id ?? 0),
      type: (parsed.type ?? type ?? "error") as InvestigationEventType,
      payload: parsed.payload ?? {},
      at: parsed.at ?? new Date().toISOString(),
    }
  } catch {
    return null
  }
}

/**
 * Streams GET /investigations/{id}/events with fetch + ReadableStream (EventSource can't send
 * an Authorization header). Reconnects with Last-Event-ID and keeps TanStack Query caches fresh.
 *
 * The backend caps open streams per user, so finished investigations are fetched in replay mode
 * (`?follow=false`): the history arrives once and the connection closes. Pass `undefined` until
 * the investigation's state is known, so no stream is opened only to be replaced.
 */
export function useInvestigationEvents(investigationId: string, mode: StreamMode | undefined = "live") {
  const qc = useQueryClient()
  const ws = useWorkspaceId()
  const [events, setEvents] = useState<InvestigationEvent[]>([])
  const [status, setStatus] = useState<StreamStatus>("connecting")
  const lastSeq = useRef(0)

  useEffect(() => {
    if (!ws || !mode) return
    lastSeq.current = 0
    setEvents([])

    const handle = (e: InvestigationEvent) => {
      if (e.seq <= lastSeq.current) return
      lastSeq.current = e.seq
      setEvents((prev) => [...prev, e])
      qc.invalidateQueries({ queryKey: qk.investigation(ws, investigationId), exact: true })
      for (const part of PART_FOR_EVENT[e.type] ?? []) {
        qc.invalidateQueries({ queryKey: qk.investigationPart(ws, investigationId, part) })
      }
      if (e.type === "approval_requested") qc.invalidateQueries({ queryKey: qk.pendingApprovals(ws) })
    }

    if (IS_MOCK && api.investigations.subscribeMockEvents) {
      setStatus("open")
      const unsubscribe = api.investigations.subscribeMockEvents(investigationId, 0, handle)
      return () => {
        unsubscribe()
        setStatus("closed")
      }
    }

    const controller = new AbortController()
    let attempt = 0

    const connect = async (): Promise<void> => {
      while (!controller.signal.aborted) {
        try {
          setStatus(attempt === 0 ? "connecting" : "reconnecting")
          const res = await fetch(`${API_BASE_URL}/investigations/${investigationId}/events${mode === "replay" ? "?follow=false" : ""}`, {
            headers: {
              Accept: "text/event-stream",
              ...authHeaders(),
              ...(lastSeq.current ? { "Last-Event-ID": String(lastSeq.current) } : {}),
            },
            credentials: "include",
            signal: controller.signal,
          })
          if (res.status === 401 && (await refreshAccessToken())) continue
          if (!res.ok || !res.body) throw new Error(`SSE HTTP ${res.status}`)
          setStatus("open")
          attempt = 0
          const reader = res.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ""
          for (;;) {
            const { value, done } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const frames = buffer.split(/\r?\n\r?\n/)
            buffer = frames.pop() ?? ""
            for (const f of frames) {
              const ev = parseSseFrame(f)
              if (ev) handle(ev)
            }
          }
          if (mode === "replay") {
            setStatus("replayed")
            return
          }
        } catch (err) {
          if (controller.signal.aborted) return
          void err
        }
        if (controller.signal.aborted) return
        attempt += 1
        setStatus("reconnecting")
        await new Promise((r) => setTimeout(r, Math.min(15_000, 1000 * 2 ** Math.min(attempt, 4))))
      }
    }

    void connect()
    return () => {
      controller.abort()
      setStatus("closed")
    }
  }, [investigationId, ws, qc, mode])

  return { events, status }
}
