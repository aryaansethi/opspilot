import { cn } from "@/lib/utils"

export function JsonViewer({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={cn("max-h-72 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed", className)}>
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

export function KeyValueList({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className="divide-y rounded-md border text-sm">
      {Object.entries(value).map(([k, v]) => (
        <div key={k} className="grid grid-cols-[minmax(90px,30%)_1fr] gap-3 px-3 py-2">
          <dt className="font-mono text-xs text-muted-foreground">{k}</dt>
          <dd className="break-words font-mono text-xs">{typeof v === "string" ? v : JSON.stringify(v)}</dd>
        </div>
      ))}
    </dl>
  )
}
