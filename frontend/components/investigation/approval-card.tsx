"use client"

import { Check, ExternalLink, Lock, X } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { AccessBadge, Pill, type Tone } from "@/components/common/badges"
import { ConfirmDialog } from "@/components/common/confirm-dialog"
import { KeyValueList } from "@/components/common/json-viewer"
import { RelativeTime } from "@/components/common/relative-time"
import { Button } from "@/components/ui/button"
import { errorMessage } from "@/lib/api/client"
import { useApprove, useReject } from "@/lib/api/endpoints/approvals"
import type { ApprovalRequest } from "@/lib/types/api"

const tone: Record<ApprovalRequest["status"], Tone> = { pending: "warning", approved: "info", rejected: "neutral", executed: "success", failed: "danger" }

export function ApprovalCard({ approval }: { approval: ApprovalRequest }) {
  const approve = useApprove()
  const reject = useReject()
  const [confirm, setConfirm] = useState(false)
  const a = approval

  const doApprove = async () => {
    try {
      const res = await approve.mutateAsync(a.id)
      setConfirm(false)
      toast.success(res.result?.key ? `Created ${res.result.key}` : "Action approved")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  const doReject = async () => {
    try {
      await reject.mutateAsync(a.id)
      toast("Action rejected — nothing was executed")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }

  return (
    <div className={a.status === "pending" ? "rounded-lg border border-warning/40 bg-card" : "rounded-lg border bg-card"}>
      <div className="flex items-center gap-2 border-b px-3 py-2">
        <Lock className="size-3.5 text-warning" aria-hidden />
        <span className="min-w-0 flex-1 truncate font-mono text-xs">
          <span className="text-muted-foreground">{a.server}.</span>
          {a.tool}
        </span>
        <AccessBadge access="write" />
        <Pill tone={tone[a.status]} className="capitalize">
          {a.status}
        </Pill>
      </div>
      <div className="space-y-2 p-3">
        <p className="text-[11px] text-muted-foreground">Exact arguments that will be sent</p>
        <KeyValueList value={a.arguments} />
        <p className="text-[11px] text-muted-foreground">Requested by {a.requested_by.display_name}</p>
        {a.status === "pending" ? (
          <div className="flex gap-2 pt-1">
            <Button size="sm" className="flex-1" onClick={() => setConfirm(true)}>
              <Check /> Approve
            </Button>
            <Button size="sm" variant="outline" className="flex-1" onClick={doReject} disabled={reject.isPending}>
              <X /> Reject
            </Button>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            {a.decided_by && (
              <p>
                {a.status === "rejected" ? "Rejected" : "Approved"} by {a.decided_by.display_name}
                {a.decided_at && (
                  <>
                    {" "}
                    · <RelativeTime iso={a.decided_at} />
                  </>
                )}
              </p>
            )}
            {a.result?.url && (
              <a href={a.result.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-1 font-mono text-primary hover:underline">
                {a.result.key ?? "Open result"} <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        )}
      </div>
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title="Run this write action?"
        description={
          <>
            OpsPilot will call <span className="font-mono text-foreground">{a.server}.{a.tool}</span> with exactly these arguments. This approval
            covers this one action only.
          </>
        }
        confirmLabel="Approve and run"
        busy={approve.isPending}
        onConfirm={doApprove}
      >
        <KeyValueList value={a.arguments} />
      </ConfirmDialog>
    </div>
  )
}
