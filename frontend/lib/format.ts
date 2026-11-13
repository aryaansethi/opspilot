import { format, formatDistanceToNowStrict } from "date-fns"

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 ** 2).toFixed(1)} MB`
}

export function relativeTime(iso: string): string {
  return `${formatDistanceToNowStrict(new Date(iso))} ago`
}

export function absoluteTime(iso: string): string {
  return format(new Date(iso), "yyyy-MM-dd HH:mm:ss")
}

export function shortTime(iso: string): string {
  return format(new Date(iso), "MMM d, HH:mm")
}

export function humanize(s: string): string {
  return s.toLowerCase().replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase())
}

export function formatMetric(v: number | undefined, kind: "ratio" | "ms" = "ratio"): string {
  if (v === undefined || v === null) return "—"
  return kind === "ms" ? `${Math.round(v)} ms` : v.toFixed(3)
}
