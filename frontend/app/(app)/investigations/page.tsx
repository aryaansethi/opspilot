"use client"

import { Plus, Siren } from "lucide-react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useState } from "react"
import { InvestigationStateBadge } from "@/components/common/badges"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { FilterSelect } from "@/components/common/filter-select"
import { PageHeader } from "@/components/common/page-header"
import { RelativeTime } from "@/components/common/relative-time"
import { ListSkeleton } from "@/components/common/skeletons"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useInvestigations } from "@/lib/api/endpoints/investigations"
import type { InvestigationState } from "@/lib/types/api"

const STATE_FILTERS: { value: InvestigationState; label: string }[] = [
  { value: "AWAITING_PARAMETERS", label: "Needs input" },
  { value: "COMPLETED", label: "Completed" },
  { value: "PARTIAL", label: "Partial" },
  { value: "FAILED_LLM", label: "Failed (LLM)" },
  { value: "FAILED_RETRIEVAL", label: "Failed (retrieval)" },
]

export default function InvestigationsPage() {
  const router = useRouter()
  const [state, setState] = useState<InvestigationState>()
  const inv = useInvestigations({ state })
  const items = inv.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Investigations"
        description="Every investigation keeps its evidence, tool calls and report."
        actions={
          <Button asChild>
            <Link href="/investigations/new">
              <Plus /> New investigation
            </Link>
          </Button>
        }
      />
      <div className="mb-4">
        <FilterSelect label="Filter by state" allLabel="All states" value={state} onChange={setState} options={STATE_FILTERS} />
      </div>
      {inv.isLoading ? (
        <ListSkeleton rows={6} />
      ) : inv.isError ? (
        <ErrorState error={inv.error} onRetry={() => inv.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Siren}
          title={state ? "No investigations in this state" : "No investigations yet"}
          description={state ? undefined : "Describe an incident and OpsPilot will gather and cite the evidence."}
          action={
            !state && (
              <Button asChild>
                <Link href="/investigations/new">New investigation</Link>
              </Button>
            )
          }
        />
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Question</TableHead>
                <TableHead className="hidden md:table-cell">Service</TableHead>
                <TableHead className="hidden lg:table-cell">Env</TableHead>
                <TableHead>State</TableHead>
                <TableHead className="hidden lg:table-cell">Created by</TableHead>
                <TableHead className="hidden sm:table-cell">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((i) => (
                <TableRow key={i.id} className="cursor-pointer" onClick={() => router.push(`/investigations/${i.id}`)}>
                  <TableCell className="max-w-[420px]">
                    <Link href={`/investigations/${i.id}`} className="block truncate font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                      {i.question}
                    </Link>
                  </TableCell>
                  <TableCell className="hidden font-mono text-xs md:table-cell">{i.service ?? "—"}</TableCell>
                  <TableCell className="hidden text-xs lg:table-cell">{i.environment ?? "—"}</TableCell>
                  <TableCell>
                    <InvestigationStateBadge state={i.state} />
                  </TableCell>
                  <TableCell className="hidden text-xs lg:table-cell">{i.created_by?.display_name ?? "—"}</TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground sm:table-cell">
                    <RelativeTime iso={i.updated_at} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  )
}
