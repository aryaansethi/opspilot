"use client"

import { ArrowRight, BookOpen, CheckCircle2, Plug, Plus, ShieldAlert, Siren, Upload } from "lucide-react"
import Link from "next/link"
import { InvestigationStateBadge, isRunning } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { PageHeader } from "@/components/common/page-header"
import { RelativeTime } from "@/components/common/relative-time"
import { ListSkeleton } from "@/components/common/skeletons"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { usePendingApprovals } from "@/lib/api/endpoints/approvals"
import { useDocuments } from "@/lib/api/endpoints/documents"
import { useIntegrations } from "@/lib/api/endpoints/integrations"
import { useInvestigations } from "@/lib/api/endpoints/investigations"
import { useAuth } from "@/lib/auth/auth-provider"
import type { DocStatus } from "@/lib/types/api"

function Stat({ label, value, hint, icon: Icon, href, loading }: { label: string; value: number | string; hint?: string; icon: typeof Siren; href: string; loading: boolean }) {
  return (
    <Link href={href} className="group rounded-lg border bg-card p-4 transition-colors hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        {label}
        <Icon className="size-4" aria-hidden />
      </div>
      {loading ? <Skeleton className="mt-2 h-7 w-12" /> : <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>}
      {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
    </Link>
  )
}

export default function DashboardPage() {
  const { user, workspace } = useAuth()
  const inv = useInvestigations()
  const docs = useDocuments()
  const approvals = usePendingApprovals()
  const ints = useIntegrations()

  const items = inv.data?.items ?? []
  const active = items.filter((i) => isRunning(i.state) || i.state === "AWAITING_PARAMETERS").length
  const docItems = docs.data?.items ?? []
  const byStatus = docItems.reduce<Partial<Record<DocStatus, number>>>((acc, d) => ({ ...acc, [d.status]: (acc[d.status] ?? 0) + 1 }), {})
  const connected = (ints.data ?? []).filter((i) => i.status === "connected").length

  return (
    <>
      <PageHeader
        title={`Hi, ${user?.display_name.split(" ")[0] ?? "there"}`}
        description={`Overview of ${workspace?.name ?? "your workspace"}`}
        actions={
          <Button asChild>
            <Link href="/investigations/new">
              <Plus /> New investigation
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Active investigations" value={active} hint={`${items.length} total`} icon={Siren} href="/investigations" loading={inv.isLoading} />
        <Stat label="Pending approvals" value={approvals.data?.length ?? 0} hint="Write actions awaiting review" icon={ShieldAlert} href="/investigations" loading={approvals.isLoading} />
        <Stat label="Indexed documents" value={byStatus.indexed ?? 0} hint={`${docItems.length} uploaded`} icon={BookOpen} href="/knowledge" loading={docs.isLoading} />
        <Stat label="Connected integrations" value={connected} hint={`${ints.data?.length ?? 0} configured`} icon={Plug} href="/integrations" loading={ints.isLoading} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Recent investigations</CardTitle>
            <CardAction>
              <Button variant="ghost" size="sm" asChild>
                <Link href="/investigations">
                  View all <ArrowRight />
                </Link>
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent>
            {inv.isLoading ? (
              <ListSkeleton rows={4} />
            ) : inv.isError ? (
              <ErrorState error={inv.error} onRetry={() => inv.refetch()} />
            ) : items.length === 0 ? (
              <EmptyState
                icon={Siren}
                title="No investigations yet"
                description="Describe an incident and OpsPilot will gather evidence for you."
                action={
                  <Button size="sm" asChild>
                    <Link href="/investigations/new">Start one</Link>
                  </Button>
                }
              />
            ) : (
              <ul className="divide-y">
                {items.slice(0, 5).map((i) => (
                  <li key={i.id}>
                    <Link href={`/investigations/${i.id}`} className="flex flex-col gap-1 py-3 hover:bg-muted/30 sm:flex-row sm:items-center sm:gap-4 sm:px-2">
                      <span className="min-w-0 flex-1 truncate text-sm">{i.question}</span>
                      <span className="flex items-center gap-3 text-xs text-muted-foreground">
                        {i.service && <span className="font-mono">{i.service}</span>}
                        <InvestigationStateBadge state={i.state} />
                        <RelativeTime iso={i.updated_at} />
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Knowledge base</CardTitle>
            </CardHeader>
            <CardContent>
              {docs.isLoading ? (
                <ListSkeleton rows={2} />
              ) : docs.isError ? (
                <ErrorState error={docs.error} onRetry={() => docs.refetch()} />
              ) : docItems.length === 0 ? (
                <EmptyState
                  icon={Upload}
                  title="Upload your first runbook"
                  description="Runbooks, architecture docs and postmortems make investigations far better."
                  action={
                    <Button size="sm" variant="outline" asChild>
                      <Link href="/knowledge">Go to knowledge base</Link>
                    </Button>
                  }
                />
              ) : (
                <dl className="grid grid-cols-2 gap-3 text-sm">
                  {(["indexed", "processing", "queued", "failed"] as DocStatus[]).map((s) => (
                    <div key={s} className="rounded-md border p-3">
                      <dt className="text-xs text-muted-foreground capitalize">{s}</dt>
                      <dd className="text-lg font-semibold tabular-nums">{byStatus[s] ?? 0}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Integrations</CardTitle>
            </CardHeader>
            <CardContent>
              {ints.isLoading ? (
                <ListSkeleton rows={2} />
              ) : ints.isError ? (
                <ErrorState error={ints.error} onRetry={() => ints.refetch()} />
              ) : (ints.data ?? []).length === 0 ? (
                <EmptyState icon={Plug} title="No tools connected" description="Connect GitHub or CloudWatch to add live evidence." />
              ) : (
                <ul className="space-y-2 text-sm">
                  {ints.data?.map((i) => (
                    <li key={i.id} className="flex items-center justify-between">
                      <span>{{ github: "GitHub", cloudwatch: "AWS CloudWatch", jira: "Jira" }[i.kind]}</span>
                      <span className={`flex items-center gap-1 text-xs ${i.status === "connected" ? "text-success" : "text-destructive"}`}>
                        <CheckCircle2 className="size-3.5" /> {i.status}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  )
}
