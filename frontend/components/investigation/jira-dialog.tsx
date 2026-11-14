"use client"

import { Loader2 } from "lucide-react"
import { useEffect, useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/client"
import { useRequestAction } from "@/lib/api/endpoints/investigations"
import type { Investigation, JiraIssueFields, Report } from "@/lib/types/api"

function draft(inv: Investigation, report: Report): JiraIssueFields {
  return {
    project: "OPS",
    issue_type: "Incident",
    summary: (inv.service && !inv.question.toLowerCase().startsWith(inv.service.toLowerCase()) ? `${inv.service}: ${inv.question}` : inv.question).slice(0, 120),
    description: [report.overview, "", "Observed facts:", ...report.observed_facts.map((f) => `- ${f.text}`), "", "Recommended diagnostics:", ...report.recommended_diagnostics.map((d) => `- ${d}`)].join("\n"),
    labels: [inv.incident_type, inv.service].filter(Boolean) as string[],
  }
}

export function JiraDialog({ open, onOpenChange, investigation, report }: { open: boolean; onOpenChange: (v: boolean) => void; investigation: Investigation; report: Report }) {
  const req = useRequestAction(investigation.id)
  const [f, setF] = useState<JiraIssueFields>(() => draft(investigation, report))
  const [labels, setLabels] = useState(f.labels.join(", "))

  useEffect(() => {
    if (open) {
      const d = draft(investigation, report)
      setF(d)
      setLabels(d.labels.join(", "))
    }
  }, [open, investigation, report])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    try {
      await req.mutateAsync({
        kind: "create_jira_issue",
        fields: { ...f, labels: labels.split(",").map((l) => l.trim()).filter(Boolean) },
      })
      toast.success("Sent for approval — nothing has been created yet")
      onOpenChange(false)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Propose a Jira ticket</DialogTitle>
          <DialogDescription>This creates an approval request. The ticket is only created after someone approves the exact fields below.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1.5">
              <Label htmlFor="j-project">Project</Label>
              <Input id="j-project" value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })} className="font-mono" required />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="j-type">Issue type</Label>
              <Input id="j-type" value={f.issue_type} onChange={(e) => setF({ ...f, issue_type: e.target.value })} required />
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="j-summary">Summary</Label>
            <Input id="j-summary" value={f.summary} maxLength={255} onChange={(e) => setF({ ...f, summary: e.target.value })} required />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="j-desc">Description</Label>
            <Textarea id="j-desc" rows={7} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} className="font-mono text-xs" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="j-labels">Labels (comma-separated)</Label>
            <Input id="j-labels" value={labels} onChange={(e) => setLabels(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={req.isPending || !f.summary.trim() || !f.project.trim()}>
              {req.isPending && <Loader2 className="animate-spin" />}
              Request approval
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
