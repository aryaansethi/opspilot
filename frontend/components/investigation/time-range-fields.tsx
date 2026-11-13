"use client"

import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

export type TimePreset = "none" | "1h" | "6h" | "24h" | "custom"

export interface TimeRangeValue {
  preset: TimePreset
  start: string // datetime-local value
  end: string
}

const HOURS: Record<Exclude<TimePreset, "none" | "custom">, number> = { "1h": 1, "6h": 6, "24h": 24 }

/** Resolve the selection to ISO timestamps (undefined if no range chosen or incomplete). */
export function resolveRange(v: TimeRangeValue): { time_start?: string; time_end?: string } {
  if (v.preset === "none") return {}
  if (v.preset === "custom") {
    if (!v.start || !v.end) return {}
    return { time_start: new Date(v.start).toISOString(), time_end: new Date(v.end).toISOString() }
  }
  const end = new Date()
  const start = new Date(end.getTime() - HOURS[v.preset] * 3_600_000)
  return { time_start: start.toISOString(), time_end: end.toISOString() }
}

export function TimeRangeFields({ value, onChange, idPrefix = "tr", allowNone = true }: { value: TimeRangeValue; onChange: (v: TimeRangeValue) => void; idPrefix?: string; allowNone?: boolean }) {
  return (
    <div className="grid gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor={`${idPrefix}-preset`}>Time range</Label>
        <Select value={value.preset} onValueChange={(p) => onChange({ ...value, preset: p as TimePreset })}>
          <SelectTrigger id={`${idPrefix}-preset`} className="w-full sm:w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {allowNone && <SelectItem value="none">Not set</SelectItem>}
            <SelectItem value="1h">Last 1 hour</SelectItem>
            <SelectItem value="6h">Last 6 hours</SelectItem>
            <SelectItem value="24h">Last 24 hours</SelectItem>
            <SelectItem value="custom">Custom…</SelectItem>
          </SelectContent>
        </Select>
      </div>
      {value.preset === "custom" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor={`${idPrefix}-start`}>Start</Label>
            <Input id={`${idPrefix}-start`} type="datetime-local" value={value.start} onChange={(e) => onChange({ ...value, start: e.target.value })} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor={`${idPrefix}-end`}>End</Label>
            <Input id={`${idPrefix}-end`} type="datetime-local" value={value.end} min={value.start} onChange={(e) => onChange({ ...value, end: e.target.value })} />
          </div>
        </div>
      )}
    </div>
  )
}
