import { describe, expect, it } from "vitest"
import { completedStartSeqs } from "@/components/investigation/activity-timeline"
import { mimeFor } from "@/lib/api/endpoints/documents"
import { toBackendFilters } from "@/lib/api/http"
import { formatMetric, safeHref } from "@/lib/format"
import { parseSseFrame } from "@/lib/sse"
import type { InvestigationEvent } from "@/lib/types/api"

describe("parseSseFrame", () => {
  it("parses id, event and JSON data", () => {
    const ev = parseSseFrame('id: 7\nevent: state_changed\ndata: {"seq":7,"type":"state_changed","payload":{"from":"A","to":"B"},"at":"2026-01-01T00:00:00Z"}')
    expect(ev).toEqual({ seq: 7, type: "state_changed", payload: { from: "A", to: "B" }, at: "2026-01-01T00:00:00Z" })
  })

  it("falls back to the frame id and event name", () => {
    const ev = parseSseFrame('id: 3\nevent: report_ready\ndata: {"payload":{"version":1}}')
    expect(ev?.seq).toBe(3)
    expect(ev?.type).toBe("report_ready")
  })

  it("joins multi-line data and handles CRLF", () => {
    const ev = parseSseFrame('id: 1\r\nevent: error\r\ndata: {"seq":1,\r\ndata: "type":"error","payload":{}}')
    expect(ev?.type).toBe("error")
  })

  it("ignores keepalive comments and malformed data", () => {
    expect(parseSseFrame(": keepalive")).toBeNull()
    expect(parseSseFrame("event: x\ndata: {not json")).toBeNull()
  })
})

describe("completedStartSeqs (activity timeline)", () => {
  const ev = (seq: number, type: InvestigationEvent["type"], tool: string): InvestigationEvent => ({ seq, type, payload: { tool }, at: "" })

  it("pairs each start with the next completion of the same tool", () => {
    const done = completedStartSeqs([
      ev(1, "tool_call_started", "cloudwatch.filter_log_events"),
      ev(2, "tool_call_started", "cloudwatch.filter_log_events"),
      ev(3, "tool_call_started", "cloudwatch.get_metric_data"),
      ev(4, "tool_call_completed", "cloudwatch.filter_log_events"),
      ev(5, "tool_call_completed", "cloudwatch.get_metric_data"),
    ])
    expect([...done].sort()).toEqual([1, 3])
  })

  it("leaves a still-running call visible", () => {
    expect(completedStartSeqs([ev(1, "tool_call_started", "github.search_code")]).size).toBe(0)
  })
})

describe("toBackendFilters", () => {
  it("maps single UI filters to the backend's lists", () => {
    expect(toBackendFilters({ source_type: "runbook", service: "orders-api", environment: "production" })).toEqual({
      source_types: ["runbook"],
      services: ["orders-api"],
      environments: ["production"],
    })
  })

  it("omits the filters object when nothing is set", () => {
    expect(toBackendFilters({})).toBeUndefined()
    expect(toBackendFilters(undefined)).toBeUndefined()
  })
})

describe("safeHref", () => {
  it("allows http(s) links from tool output", () => {
    expect(safeHref("https://github.com/acme/orders-api/commit/abc")).toBe("https://github.com/acme/orders-api/commit/abc")
    expect(safeHref("http://localhost:4566/x")).toBe("http://localhost:4566/x")
  })

  it("drops script, data and malformed URLs", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined()
    expect(safeHref(" JavaScript:alert(1)")).toBeUndefined()
    expect(safeHref("data:text/html,<script>alert(1)</script>")).toBeUndefined()
    expect(safeHref("not a url")).toBeUndefined()
    expect(safeHref(undefined)).toBeUndefined()
  })
})

describe("mimeFor (uploads)", () => {
  it("infers the type from the extension when the browser reports none", () => {
    expect(mimeFor(new File(["x"], "runbook.md", { type: "" }))).toBe("text/markdown")
    expect(mimeFor(new File(["x"], "Notes.TXT", { type: "" }))).toBe("text/plain")
    expect(mimeFor(new File(["x"], "postmortem.pdf", { type: "" }))).toBe("application/pdf")
  })
})

describe("formatMetric", () => {
  it("formats ratios and milliseconds, and shows a dash for missing values", () => {
    expect(formatMetric(0.90178)).toBe("0.902")
    expect(formatMetric(143.8, "ms")).toBe("144 ms")
    expect(formatMetric(undefined)).toBe("—")
  })
})
