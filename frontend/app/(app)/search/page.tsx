"use client"

import { AlertTriangle, Loader2, MessageSquareText, Search as SearchIcon, SearchX } from "lucide-react"
import { useState, type FormEvent } from "react"
import { SourceTypeBadge } from "@/components/common/badges"
import { CitationChip } from "@/components/common/citation-chip"
import { EmptyState } from "@/components/common/empty-state"
import { ErrorState } from "@/components/common/error-state"
import { FilterSelect } from "@/components/common/filter-select"
import { Highlight } from "@/components/common/highlight"
import { PageHeader } from "@/components/common/page-header"
import { ListSkeleton } from "@/components/common/skeletons"
import { EvidenceCard } from "@/components/investigation/evidence-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAsk, useSearch } from "@/lib/api/endpoints/search"
import type { Evidence, SearchFilters, SearchMode, SourceType } from "@/lib/types/api"
import { cn } from "@/lib/utils"

const MODES: { value: SearchMode; label: string }[] = [
  { value: "hybrid", label: "Hybrid" },
  { value: "lexical", label: "Lexical" },
  { value: "vector", label: "Vector" },
]

export default function SearchPage() {
  const [tab, setTab] = useState<"search" | "ask">("search")
  // Search and Ask keep separate text so switching tabs never merges a query into a question.
  const [texts, setTexts] = useState({ search: "", ask: "" })
  const query = texts[tab]
  const setQuery = (v: string) => setTexts((t) => ({ ...t, [tab]: v }))
  const [submitted, setSubmitted] = useState("")
  const [mode, setMode] = useState<SearchMode>("hybrid")
  const [rerank, setRerank] = useState(false)
  const [debug, setDebug] = useState(false)
  const [sourceType, setSourceType] = useState<SourceType>()
  const [service, setService] = useState("")
  const [environment, setEnvironment] = useState<string>()
  const [openCitation, setOpenCitation] = useState<{ ev: Evidence; n: number } | null>(null)
  const search = useSearch()
  const ask = useAsk()

  const filters: SearchFilters = { source_type: sourceType, service: service.trim() || undefined, environment }

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const q = query.trim()
    if (!q) return
    setSubmitted(q)
    if (tab === "search") search.mutate({ query: q, filters, top_k: 10, mode, rerank, debug })
    else ask.mutate({ question: q, filters })
  }

  const active = tab === "search" ? search : ask

  return (
    <>
      <PageHeader title="Search" description="Query your knowledge base directly, or ask a question and get a cited answer." />
      <Tabs value={tab} onValueChange={(v) => setTab(v as "search" | "ask")} className="mb-4">
        <TabsList>
          <TabsTrigger value="search">
            <SearchIcon /> Search
          </TabsTrigger>
          <TabsTrigger value="ask">
            <MessageSquareText /> Ask
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <form onSubmit={submit} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={tab === "search" ? "e.g. timeout acquiring connection from pool" : "e.g. What should I check first when orders-api latency spikes?"}
          aria-label={tab === "search" ? "Search query" : "Question"}
          className="h-10 text-base"
        />
        <Button type="submit" size="lg" className="h-10" disabled={!query.trim() || active.isPending}>
          {active.isPending ? <Loader2 className="animate-spin" /> : tab === "search" ? <SearchIcon /> : <MessageSquareText />}
          {tab === "search" ? "Search" : "Ask"}
        </Button>
      </form>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
        {tab === "search" && (
          <>
            <div role="radiogroup" aria-label="Retrieval mode" className="inline-flex rounded-lg border p-0.5">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  role="radio"
                  aria-checked={mode === m.value}
                  onClick={() => setMode(m.value)}
                  className={cn("rounded-md px-2.5 py-1 text-xs transition-colors", mode === m.value ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}
                >
                  {m.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Switch id="rerank" checked={rerank} onCheckedChange={setRerank} />
              <Label htmlFor="rerank" className="text-xs">Rerank</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="debug" checked={debug} onCheckedChange={setDebug} />
              <Label htmlFor="debug" className="text-xs">Debug ranks</Label>
            </div>
          </>
        )}
        <FilterSelect
          label="Source type"
          allLabel="All types"
          value={sourceType}
          onChange={setSourceType}
          className="w-36"
          options={[
            { value: "runbook", label: "Runbook" },
            { value: "architecture", label: "Architecture" },
            { value: "incident_report", label: "Incident report" },
            { value: "other", label: "Other" },
          ]}
        />
        <Input value={service} onChange={(e) => setService(e.target.value)} placeholder="Service…" aria-label="Service filter" className="h-7 w-32" />
        <FilterSelect
          label="Environment"
          allLabel="Any env"
          value={environment}
          onChange={setEnvironment}
          className="w-32"
          options={[
            { value: "production", label: "production" },
            { value: "staging", label: "staging" },
            { value: "development", label: "development" },
          ]}
        />
      </div>

      <div className="mt-6">
        {tab === "search" ? (
          search.isPending ? (
            <ListSkeleton rows={4} />
          ) : search.isError ? (
            <ErrorState error={search.error} onRetry={() => submit()} />
          ) : !search.data ? (
            <EmptyState icon={SearchIcon} title="Search your knowledge base" description="Exact error strings work well with Lexical; descriptions of symptoms work well with Vector. Hybrid combines both." />
          ) : search.data.results.length === 0 ? (
            <EmptyState icon={SearchX} title="No results" description="Try different wording, another mode, or fewer filters." />
          ) : (
            <>
              <p className="mb-3 text-xs text-muted-foreground">
                {search.data.results.length} results · {search.data.latency_ms} ms · {mode}
                {rerank ? " + rerank" : ""}
              </p>
              {debug && search.data.results[0]?.debug && (
                <div className="mb-4 overflow-x-auto rounded-lg border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>#</TableHead>
                        <TableHead>Chunk</TableHead>
                        <TableHead className="text-right">Lexical rank</TableHead>
                        <TableHead className="text-right">Vector rank</TableHead>
                        <TableHead className="text-right">RRF score</TableHead>
                        <TableHead className="text-right">Rerank score</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody className="font-mono text-xs">
                      {search.data.results.map((r, i) => (
                        <TableRow key={r.chunk_id}>
                          <TableCell>{i + 1}</TableCell>
                          <TableCell className="max-w-[260px] truncate font-sans">{r.document_title}</TableCell>
                          <TableCell className="text-right">{r.debug?.lexical_rank ?? "—"}</TableCell>
                          <TableCell className="text-right">{r.debug?.vector_rank ?? "—"}</TableCell>
                          <TableCell className="text-right">{r.debug?.rrf_score.toFixed(4)}</TableCell>
                          <TableCell className="text-right">{r.debug?.rerank_score?.toFixed(3) ?? "—"}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
              <ol className="space-y-3">
                {search.data.results.map((r) => (
                  <li key={r.chunk_id} className="rounded-lg border bg-card p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <SourceTypeBadge type={r.source_type} />
                      <span className="text-sm font-medium">{r.document_title}</span>
                      <span className="ml-auto font-mono text-[11px] text-muted-foreground">score {r.score.toFixed(4)}</span>
                    </div>
                    {(r.section_path || r.page_start != null) && (
                      <p className="mt-1 text-xs text-muted-foreground">
                        {r.section_path}
                        {r.page_start != null && ` · p.${r.page_start}`}
                      </p>
                    )}
                    <p className="mt-2 text-sm leading-relaxed">
                      <Highlight text={r.excerpt} query={submitted} />
                    </p>
                  </li>
                ))}
              </ol>
            </>
          )
        ) : ask.isPending ? (
          <ListSkeleton rows={3} />
        ) : ask.isError ? (
          <ErrorState error={ask.error} onRetry={() => submit()} />
        ) : !ask.data ? (
          <EmptyState icon={MessageSquareText} title="Ask a question" description="Answers are built only from your indexed documents, with a citation for every claim." />
        ) : ask.data.insufficient_evidence ? (
          <div role="status" className="flex gap-3 rounded-lg border border-warning/30 bg-warning/10 p-4">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
            <div>
              <p className="text-sm font-medium text-warning">Not enough evidence in your knowledge base</p>
              <p className="mt-1 text-sm text-muted-foreground">
                OpsPilot couldn&apos;t find sources that answer this. It won&apos;t guess. Try rephrasing, or upload the relevant runbook.
              </p>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="rounded-lg border bg-card p-5">
              <h2 className="mb-3 text-xs font-medium tracking-wide text-muted-foreground uppercase">Answer</h2>
              <div className="space-y-2 text-sm leading-relaxed">
                {ask.data.claims.map((c, i) => (
                  <p key={i}>
                    {c.text}
                    {c.evidence_ids.map((id) => {
                      const n = ask.data!.citations.findIndex((x) => x.id === id) + 1
                      const ev = ask.data!.citations[n - 1]
                      return ev ? <CitationChip key={id} n={n} onClick={() => setOpenCitation({ ev, n })} /> : null
                    })}
                  </p>
                ))}
              </div>
            </div>
            <div>
              <h2 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">Sources</h2>
              <ol className="space-y-2">
                {ask.data.citations.map((c, i) => (
                  <li key={c.id}>
                    <button type="button" onClick={() => setOpenCitation({ ev: c, n: i + 1 })} className="w-full rounded-md border p-2.5 text-left text-sm hover:bg-muted/40">
                      <span className="mr-1 font-mono text-[11px] text-primary">[{i + 1}]</span>
                      {c.title}
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </div>

      <Sheet open={!!openCitation} onOpenChange={(v) => !v && setOpenCitation(null)}>
        <SheetContent className="w-full sm:max-w-md">
          <SheetHeader>
            <SheetTitle>Citation [{openCitation?.n}]</SheetTitle>
            <SheetDescription>The retrieved source this claim is based on.</SheetDescription>
          </SheetHeader>
          <div className="px-4">{openCitation && <EvidenceCard evidence={openCitation.ev} />}</div>
        </SheetContent>
      </Sheet>
    </>
  )
}
