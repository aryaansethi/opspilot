"use client"

import { Info, Loader2 } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { PageHeader } from "@/components/common/page-header"
import { resolveRange, TimeRangeFields, type TimeRangeValue } from "@/components/investigation/time-range-fields"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/client"
import { useCreateInvestigation } from "@/lib/api/endpoints/investigations"

export default function NewInvestigationPage() {
  const router = useRouter()
  const create = useCreateInvestigation()
  const [question, setQuestion] = useState("")
  const [service, setService] = useState("")
  const [environment, setEnvironment] = useState("none")
  const [range, setRange] = useState<TimeRangeValue>({ preset: "none", start: "", end: "" })
  const [error, setError] = useState<string | null>(null)

  const resolved = resolveRange(range)
  const missing = [!service.trim() && "service", !resolved.time_start && "time range"].filter(Boolean) as string[]
  const customInvalid = range.preset === "custom" && range.start && range.end && range.end <= range.start

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (question.trim().length < 10) {
      setError("Describe the incident in at least 10 characters.")
      return
    }
    if (customInvalid) return
    setError(null)
    try {
      const { id } = await create.mutateAsync({
        question: question.trim(),
        service: service.trim() || undefined,
        environment: environment === "none" ? undefined : environment,
        ...resolved,
      })
      router.push(`/investigations/${id}`)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="New investigation" description="Describe what's happening. OpsPilot searches your knowledge base and connected tools, then reports what it found." />
      <Card>
        <CardContent>
          <form onSubmit={submit} className="grid gap-5" noValidate>
            <div className="grid gap-1.5">
              <Label htmlFor="question">What&apos;s going on?</Label>
              <Textarea
                id="question"
                rows={4}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Investigate why the API response time increased after the latest deployment…"
                aria-invalid={!!error}
              />
              {error && <p className="text-xs text-destructive">{error}</p>}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="grid gap-1.5">
                <Label htmlFor="service">Service</Label>
                <Input id="service" value={service} onChange={(e) => setService(e.target.value)} placeholder="orders-api" className="font-mono" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="environment">Environment</Label>
                <Select value={environment} onValueChange={setEnvironment}>
                  <SelectTrigger id="environment" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Not set</SelectItem>
                    <SelectItem value="production">production</SelectItem>
                    <SelectItem value="staging">staging</SelectItem>
                    <SelectItem value="development">development</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <TimeRangeFields value={range} onChange={setRange} />
            {customInvalid && <p className="-mt-3 text-xs text-destructive">End must be after start.</p>}

            {missing.length > 0 && (
              <div className="flex gap-2 rounded-md border border-info/30 bg-info/10 p-3 text-sm">
                <Info className="mt-0.5 size-4 shrink-0 text-info" aria-hidden />
                <p>
                  No {missing.join(" or ")} set. OpsPilot will ask for {missing.length > 1 ? "these" : "it"} before querying live systems — it never
                  picks a production scope on its own.
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => router.back()}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending || !question.trim()}>
                {create.isPending && <Loader2 className="animate-spin" />}
                Start investigation
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
