"use client"

import { Cloud, GitBranch, Loader2, Lock, Plug, RefreshCw, SquareKanban, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { AccessBadge, Pill } from "@/components/common/badges"
import { ConfirmDialog } from "@/components/common/confirm-dialog"
import { ErrorState } from "@/components/common/error-state"
import { PageHeader } from "@/components/common/page-header"
import { RelativeTime } from "@/components/common/relative-time"
import { CardGridSkeleton } from "@/components/common/skeletons"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { errorMessage } from "@/lib/api/client"
import { useCreateIntegration, useIntegrations, useRemoveIntegration, useSetToolEnabled, useTestIntegration } from "@/lib/api/endpoints/integrations"
import type { Integration, IntegrationKind } from "@/lib/types/api"

const META: Record<IntegrationKind, { name: string; icon: typeof Cloud; blurb: string; comingSoon?: boolean }> = {
  github: { name: "GitHub", icon: GitBranch, blurb: "Recent commits, pull requests and code search in allowlisted repositories." },
  cloudwatch: { name: "AWS CloudWatch", icon: Cloud, blurb: "Log events, metrics and alarms from allowlisted log groups and namespaces, via a read-only IAM role." },
  jira: { name: "Jira", icon: SquareKanban, blurb: "Search similar incidents; create tickets only after approval.", comingSoon: true },
}

const list = (v: unknown) => (Array.isArray(v) ? (v as string[]) : typeof v === "string" ? [v] : [])

function ConfigView({ i }: { i: Integration }) {
  const c = i.config
  const rows: [string, string[]][] =
    i.kind === "github"
      ? [
          ["Repositories", list(c.repositories)],
        ]
      : i.kind === "cloudwatch"
        ? [
            ["Region", list(c.region)],
            ["Log groups", list(c.log_groups)],
            ["Metric namespaces", list(c.namespaces)],
          ]
        : [["Projects", list(c.projects)]]
  return (
    <dl className="space-y-2 text-xs">
      {rows.map(([k, vals]) => (
        <div key={k}>
          <dt className="mb-1 text-muted-foreground">{k}</dt>
          <dd className="flex flex-wrap gap-1">
            {vals.length ? vals.map((v) => <span key={v} className="rounded border bg-muted/50 px-1.5 py-0.5 font-mono">{v}</span>) : <span className="text-muted-foreground">—</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function IntegrationCard({ i }: { i: Integration }) {
  const m = META[i.kind]
  const test = useTestIntegration()
  const remove = useRemoveIntegration()
  const setTool = useSetToolEnabled()
  const [confirmRemove, setConfirmRemove] = useState(false)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <m.icon className="size-4" aria-hidden /> {m.name}
        </CardTitle>
        <CardDescription>{m.blurb}</CardDescription>
        <CardAction>
          <Pill tone={i.status === "connected" ? "success" : i.status === "error" ? "danger" : "neutral"} className="capitalize">
            {i.status}
          </Pill>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <ConfigView i={i} />
        <div>
          <p className="mb-1.5 text-xs text-muted-foreground">Exposed tools</p>
          <ul className="divide-y rounded-md border">
            {i.tools.map((t) => (
              <li key={t.name} className="flex items-center gap-2 px-2.5 py-1.5">
                <span className="flex-1 truncate font-mono text-xs">{t.name}</span>
                <AccessBadge access={t.access} />
                {t.access === "write" && (
                  <span className="hidden items-center gap-1 text-[10px] text-muted-foreground sm:flex" title="Requires approval">
                    <Lock className="size-3" /> Requires approval
                  </span>
                )}
                <Switch
                  checked={t.enabled}
                  aria-label={`${t.enabled ? "Disable" : "Enable"} ${t.name}`}
                  disabled={setTool.isPending}
                  onCheckedChange={(enabled) =>
                    setTool.mutate({ id: i.id, tool: t.name, enabled }, { onError: (e) => toast.error(errorMessage(e)) })
                  }
                />
              </li>
            ))}
            {i.tools.length === 0 && <li className="px-2.5 py-2 text-xs text-muted-foreground">No tools reported by this server yet.</li>}
          </ul>
        </div>
      </CardContent>
      <CardFooter className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{i.last_checked_at ? <>Checked <RelativeTime iso={i.last_checked_at} /></> : "Never checked"}</span>
        <div className="flex gap-1.5">
          <Button
            size="sm"
            variant="outline"
            disabled={test.isPending}
            onClick={() =>
              test.mutate(i.id, {
                onSuccess: (r) => (r.status === "connected" ? toast.success(`${m.name} connection OK`) : toast.error(`${m.name}: ${r.status}`)),
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            {test.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} Test connection
          </Button>
          <Button size="sm" variant="ghost" aria-label={`Disconnect ${m.name}`} onClick={() => setConfirmRemove(true)}>
            <Trash2 />
          </Button>
        </div>
      </CardFooter>
      <ConfirmDialog
        open={confirmRemove}
        onOpenChange={setConfirmRemove}
        title={`Disconnect ${m.name}?`}
        description="Its tools will no longer be available to investigations. Stored credentials are deleted."
        confirmLabel="Disconnect"
        destructive
        busy={remove.isPending}
        onConfirm={() =>
          remove.mutate(i.id, {
            onSuccess: () => {
              toast.success(`${m.name} disconnected`)
              setConfirmRemove(false)
            },
            onError: (e) => toast.error(errorMessage(e)),
          })
        }
      />
    </Card>
  )
}

const splitList = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)

function ConnectDialog({ kind, onOpenChange }: { kind: IntegrationKind | null; onOpenChange: (v: boolean) => void }) {
  const create = useCreateIntegration()
  const [a, setA] = useState("")
  const [b, setB] = useState("")
  const [c, setC] = useState("")

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!kind) return
    const config =
      kind === "github"
        ? { repositories: splitList(b) }
        : { ...(a.trim() ? { region: a.trim() } : {}), log_groups: splitList(b), namespaces: splitList(c) }
    try {
      await create.mutateAsync({ kind, config })
      toast.success(`${META[kind].name} connected`)
      setA("")
      setB("")
      setC("")
      onOpenChange(false)
    } catch (err) {
      toast.error(errorMessage(err))
    }
  }

  return (
    <Dialog open={!!kind} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Connect {kind ? META[kind].name : ""}</DialogTitle>
          <DialogDescription>Read-only access, limited to the allowlist below. Credentials stay on the backend.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          {kind === "github" ? (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor="c-repos">Allowed repositories (comma or newline separated)</Label>
                <Input id="c-repos" value={b} onChange={(e) => setB(e.target.value)} placeholder="acme/orders-api, acme/billing-svc" required className="font-mono" />
              </div>
              <p className="text-xs text-muted-foreground">Uses the read-only GitHub token configured on the backend — no token is entered here.</p>
            </>
          ) : (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor="c-region">AWS region</Label>
                <Input id="c-region" value={a} onChange={(e) => setA(e.target.value)} placeholder="us-east-1 (optional)" className="font-mono" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="c-lg">Allowed log groups</Label>
                <Input id="c-lg" value={b} onChange={(e) => setB(e.target.value)} placeholder="/ecs/orders-api" required className="font-mono" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="c-ns">Allowed metric namespaces</Label>
                <Input id="c-ns" value={c} onChange={(e) => setC(e.target.value)} placeholder="AWS/ApplicationELB, AWS/RDS" required className="font-mono" />
              </div>
              <p className="text-xs text-muted-foreground">Uses the backend&apos;s IAM task role — no AWS keys are entered here.</p>
            </>
          )}
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending && <Loader2 className="animate-spin" />}
              Connect
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function IntegrationsPage() {
  const ints = useIntegrations()
  const [connecting, setConnecting] = useState<IntegrationKind | null>(null)

  return (
    <>
      <PageHeader title="Integrations" description="Live systems OpsPilot can read from during investigations, through MCP servers you control." />
      {ints.isLoading ? (
        <CardGridSkeleton />
      ) : ints.isError ? (
        <ErrorState error={ints.error} onRetry={() => ints.refetch()} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(Object.keys(META) as IntegrationKind[]).map((kind) => {
            const existing = ints.data?.find((i) => i.kind === kind)
            if (existing) return <IntegrationCard key={kind} i={existing} />
            const m = META[kind]
            return (
              <Card key={kind} className="border-dashed">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <m.icon className="size-4" aria-hidden /> {m.name}
                  </CardTitle>
                  <CardDescription>{m.blurb}</CardDescription>
                  <CardAction>{m.comingSoon ? <Pill>Coming soon</Pill> : <Pill>Not connected</Pill>}</CardAction>
                </CardHeader>
                <CardFooter className="mt-auto">
                  <Button variant="outline" size="sm" disabled={m.comingSoon} onClick={() => setConnecting(kind)}>
                    <Plug /> Connect
                  </Button>
                </CardFooter>
              </Card>
            )
          })}
        </div>
      )}
      <ConnectDialog kind={connecting} onOpenChange={(v) => !v && setConnecting(null)} />
    </>
  )
}
