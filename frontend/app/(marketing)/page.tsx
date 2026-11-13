import { ArrowRight, BarChart3, BookOpen, FileCheck2, Network, ShieldCheck, Workflow } from "lucide-react"
import Link from "next/link"
import { Logo } from "@/components/layout/logo"
import { Button } from "@/components/ui/button"

const steps = [
  { title: "Retrieve", body: "Hybrid search over your runbooks, architecture docs and past incidents — keyword and semantic, fused and reranked." },
  { title: "Correlate", body: "Pulls live evidence from GitHub and CloudWatch through read-only MCP tools, scoped to the service and time window you confirm." },
  { title: "Report", body: "Separates observed facts from hypotheses, cites every claim, and lists what evidence is still missing." },
]

const features = [
  { icon: BookOpen, title: "Hybrid search", body: "Lexical + vector retrieval with Reciprocal Rank Fusion and optional cross-encoder reranking." },
  { icon: Network, title: "Live tool evidence via MCP", body: "Commits, PRs, logs and metrics fetched through an allowlisted tool registry with timeouts and size caps." },
  { icon: ShieldCheck, title: "Human-approved actions", body: "Write actions like creating a Jira ticket show the exact arguments and wait for your approval." },
  { icon: FileCheck2, title: "Auditable reports", body: "Every tool call and approval is recorded. Every finding links back to its source." },
  { icon: BarChart3, title: "Measured retrieval quality", body: "Recall, MRR and nDCG compared across retrieval strategies on a versioned evaluation set." },
  { icon: Workflow, title: "Bounded workflow", body: "A visible state machine, not an open-ended agent. You always know which step it's on." },
]

const pipeline = ["Your question", "Hybrid RAG", "MCP read tools", "Evidence", "Hypotheses", "Cited report"]

export default function LandingPage() {
  return (
    <div className="min-h-svh">
      <header className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <Logo />
        <nav className="flex items-center gap-2">
          <Button variant="ghost" asChild>
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild>
            <Link href="/register">Get started</Link>
          </Button>
        </nav>
      </header>

      <main>
        <section className="relative overflow-hidden">
          <div className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[420px] bg-[radial-gradient(ellipse_at_top,color-mix(in_oklch,var(--primary)_18%,transparent),transparent_65%)]" />
          <div className="mx-auto max-w-4xl px-4 pt-20 pb-16 text-center sm:px-6 sm:pt-28">
            <p className="mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs text-muted-foreground">
              Incident investigation assistant for engineering teams
            </p>
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-6xl">Investigate incidents with evidence, not guesses</h1>
            <p className="mx-auto mt-5 max-w-2xl text-base text-pretty text-muted-foreground sm:text-lg">
              Describe what&apos;s wrong. OpsPilot searches your internal knowledge, gathers live evidence from your tools, and hands you a report
              that shows its sources — and admits what it doesn&apos;t know.
            </p>
            <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
              <Button size="lg" asChild>
                <Link href="/register">
                  Start an investigation <ArrowRight />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/login">Sign in</Link>
              </Button>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6" aria-labelledby="how">
          <h2 id="how" className="mb-8 text-sm font-medium tracking-wide text-muted-foreground uppercase">
            How it works
          </h2>
          <ol className="grid gap-4 md:grid-cols-3">
            {steps.map((s, i) => (
              <li key={s.title} className="rounded-lg border bg-card p-5">
                <span className="font-mono text-xs text-primary">0{i + 1}</span>
                <h3 className="mt-2 font-medium">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6" aria-labelledby="features">
          <h2 id="features" className="mb-8 text-sm font-medium tracking-wide text-muted-foreground uppercase">
            What you get
          </h2>
          <div className="grid gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {features.map(({ icon: Icon, title, body }) => (
              <div key={title} className="bg-background p-6">
                <Icon className="size-5 text-primary" aria-hidden />
                <h3 className="mt-3 font-medium">{title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6" aria-labelledby="arch">
          <h2 id="arch" className="mb-8 text-sm font-medium tracking-wide text-muted-foreground uppercase">
            Under the hood
          </h2>
          <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-5">
            {pipeline.map((p, i) => (
              <span key={p} className="flex items-center gap-2">
                <span className="rounded-md border bg-background px-3 py-1.5 font-mono text-xs">{p}</span>
                {i < pipeline.length - 1 && <ArrowRight className="size-3.5 text-muted-foreground" aria-hidden />}
              </span>
            ))}
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-4 pt-8 pb-24 sm:px-6">
          <div className="flex flex-col items-start justify-between gap-4 rounded-lg border bg-card p-8 sm:flex-row sm:items-center">
            <div>
              <h2 className="text-lg font-semibold">Bring your runbooks. Connect your tools.</h2>
              <p className="mt-1 text-sm text-muted-foreground">Read-only by default. Nothing is written without your approval.</p>
            </div>
            <Button size="lg" asChild>
              <Link href="/register">Create a workspace</Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-6 text-xs text-muted-foreground sm:px-6">
          <Logo withText />
          <span>An investigation assistant — not an autonomous operator.</span>
        </div>
      </footer>
    </div>
  )
}
