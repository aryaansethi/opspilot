"use client"

import { ChevronRight, Loader2, ScrollText } from "lucide-react"
import { Fragment, useState } from "react"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { JsonViewer } from "@/components/common/json-viewer"
import { PageHeader } from "@/components/common/page-header"
import { ListSkeleton } from "@/components/common/skeletons"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useAuditEvents } from "@/lib/api/endpoints/audit"
import { absoluteTime } from "@/lib/format"
import { cn } from "@/lib/utils"

export default function AuditPage() {
  const [actor, setActor] = useState("")
  const [action, setAction] = useState("")
  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [expanded, setExpanded] = useState<string | null>(null)
  const q = useAuditEvents({
    actor: actor.trim() || undefined,
    action: action.trim() || undefined,
    from: from ? new Date(from).toISOString() : undefined,
    to: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
  })
  const items = q.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <>
      <PageHeader title="Audit log" description="Every tool call, approval and change in this workspace." />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="grid gap-1">
          <Label htmlFor="a-actor" className="text-xs">Actor</Label>
          <Input id="a-actor" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Name" className="h-8 w-40" />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="a-action" className="text-xs">Action</Label>
          <Input id="a-action" value={action} onChange={(e) => setAction(e.target.value)} placeholder="tool.invoked" className="h-8 w-40 font-mono" />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="a-from" className="text-xs">From</Label>
          <Input id="a-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-8 w-40" />
        </div>
        <div className="grid gap-1">
          <Label htmlFor="a-to" className="text-xs">To</Label>
          <Input id="a-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-8 w-40" />
        </div>
      </div>

      {q.isLoading ? (
        <ListSkeleton rows={8} />
      ) : q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState icon={ScrollText} title="No audit events" description="Events appear as people and investigations use the workspace." />
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8">
                    <span className="sr-only">Expand</span>
                  </TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead>Actor</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Target</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((e) => {
                  const open = expanded === e.id
                  return (
                    <Fragment key={e.id}>
                      <TableRow>
                        <TableCell>
                          <Button variant="ghost" size="icon-xs" aria-expanded={open} aria-label={open ? "Hide details" : "Show details"} onClick={() => setExpanded(open ? null : e.id)}>
                            <ChevronRight className={cn("transition-transform", open && "rotate-90")} />
                          </Button>
                        </TableCell>
                        <TableCell className="font-mono text-xs whitespace-nowrap">{absoluteTime(e.created_at)}</TableCell>
                        <TableCell className="text-sm">{e.actor.display_name}</TableCell>
                        <TableCell className="font-mono text-xs">{e.action}</TableCell>
                        <TableCell className="font-mono text-xs text-muted-foreground">
                          {e.target_type}:{e.target_id}
                        </TableCell>
                      </TableRow>
                      {open && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell />
                          <TableCell colSpan={4}>
                            <JsonViewer value={e.metadata} />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  )
                })}
              </TableBody>
            </Table>
          </div>
          {q.hasNextPage && (
            <div className="mt-4 flex justify-center">
              <Button variant="outline" onClick={() => q.fetchNextPage()} disabled={q.isFetchingNextPage}>
                {q.isFetchingNextPage && <Loader2 className="animate-spin" />}
                Load more
              </Button>
            </div>
          )}
        </>
      )}
    </>
  )
}
