"use client"

import { Loader2, PauseCircle } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { errorMessage } from "@/lib/api/client"
import { useContinueInvestigation } from "@/lib/api/endpoints/investigations"
import type { Investigation } from "@/lib/types/api"
import { resolveRange, TimeRangeFields, type TimeRangeValue } from "./time-range-fields"

export function ParametersForm({ investigation }: { investigation: Investigation }) {
  const missing = investigation.missing_parameters ?? []
  const cont = useContinueInvestigation(investigation.id)
  const [service, setService] = useState(investigation.service ?? "")
  const [environment, setEnvironment] = useState(investigation.environment ?? "production")
  const [range, setRange] = useState<TimeRangeValue>({ preset: "1h", start: "", end: "" })

  const resolved = resolveRange(range)
  const valid = (!missing.includes("service") || service.trim()) && (!missing.includes("time_range") || resolved.time_start)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await cont.mutateAsync({
        ...(missing.includes("service") ? { service: service.trim() } : {}),
        ...(missing.includes("environment") || missing.includes("service") ? { environment } : {}),
        ...(missing.includes("time_range") ? resolved : {}),
      })
      toast.success("Resuming investigation")
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-warning/40 bg-warning/5 p-3">
      <div className="flex items-start gap-2">
        <PauseCircle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
        <div>
          <p className="text-sm font-medium">OpsPilot needs a bit more scope</p>
          <p className="text-xs text-muted-foreground">It won&apos;t query live systems without a confirmed service and time window.</p>
        </div>
      </div>
      {missing.includes("service") && (
        <div className="grid gap-1.5">
          <Label htmlFor="p-service">Service</Label>
          <Input id="p-service" value={service} onChange={(e) => setService(e.target.value)} placeholder="checkout-api" className="font-mono" />
        </div>
      )}
      {(missing.includes("environment") || missing.includes("service")) && (
        <div className="grid gap-1.5">
          <Label htmlFor="p-env">Environment</Label>
          <Select value={environment} onValueChange={setEnvironment}>
            <SelectTrigger id="p-env" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="production">production</SelectItem>
              <SelectItem value="staging">staging</SelectItem>
              <SelectItem value="development">development</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}
      {missing.includes("time_range") && <TimeRangeFields value={range} onChange={setRange} idPrefix="p-tr" allowNone={false} />}
      <Button type="submit" size="sm" className="w-full" disabled={!valid || cont.isPending}>
        {cont.isPending && <Loader2 className="animate-spin" />}
        Continue investigation
      </Button>
    </form>
  )
}
