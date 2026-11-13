import { cn } from "@/lib/utils"

export function CitationChip({ n, onClick, tone = "neutral", label }: { n: number | string; onClick?: () => void; tone?: "neutral" | "support" | "contradict"; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label ?? `Open citation ${n}`}
      className={cn(
        "mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded px-1 align-[1px] font-mono text-[10px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
        tone === "neutral" && "bg-primary/15 text-primary hover:bg-primary/25",
        tone === "support" && "bg-success/15 text-success hover:bg-success/25",
        tone === "contradict" && "bg-destructive/15 text-destructive hover:bg-destructive/25",
      )}
    >
      {n}
    </button>
  )
}
