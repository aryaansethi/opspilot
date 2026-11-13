"use client"

import { CheckCircle2, FileText, Loader2, UploadCloud, X, XCircle } from "lucide-react"
import { useRef, useState, type DragEvent } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { errorMessage } from "@/lib/api/client"
import { useUploadDocument } from "@/lib/api/endpoints/documents"
import { formatBytes } from "@/lib/format"
import type { SourceType } from "@/lib/types/api"
import { cn } from "@/lib/utils"

export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
const ACCEPTED = [".pdf", ".md", ".markdown", ".txt"]

export function validateFile(f: File): string | null {
  const ext = f.name.slice(f.name.lastIndexOf(".")).toLowerCase()
  if (!ACCEPTED.includes(ext)) return "Unsupported type — use PDF, Markdown or TXT"
  if (f.size === 0) return "File is empty"
  if (f.size > MAX_UPLOAD_BYTES) return `Larger than ${formatBytes(MAX_UPLOAD_BYTES)}`
  return null
}

type ItemState = { file: File; error: string | null; stage: "ready" | "uploading" | "finalizing" | "done" | "failed"; pct: number; message?: string }

export function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [items, setItems] = useState<ItemState[]>([])
  const [sourceType, setSourceType] = useState<SourceType>("runbook")
  const [service, setService] = useState("")
  const [environment, setEnvironment] = useState("")
  const [dragging, setDragging] = useState(false)
  const [running, setRunning] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const upload = useUploadDocument()

  const addFiles = (files: FileList | File[]) => {
    const next = Array.from(files).map<ItemState>((file) => ({ file, error: validateFile(file), stage: "ready", pct: 0 }))
    setItems((prev) => [...prev, ...next])
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files)
  }

  const update = (idx: number, patch: Partial<ItemState>) => setItems((prev) => prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)))

  const start = async () => {
    setRunning(true)
    let ok = 0
    for (let i = 0; i < items.length; i++) {
      const it = items[i]
      if (it.error || it.stage === "done") continue
      update(i, { stage: "uploading", pct: 0 })
      try {
        await upload.mutateAsync({
          file: it.file,
          meta: { source_type: sourceType, service: service.trim() || undefined, environment: environment || undefined },
          onProgress: (stage, pct) => update(i, { stage, pct }),
        })
        update(i, { stage: "done", pct: 100 })
        ok++
      } catch (e) {
        update(i, { stage: "failed", message: errorMessage(e) })
      }
    }
    setRunning(false)
    if (ok) toast.success(`${ok} file${ok > 1 ? "s" : ""} queued for indexing`)
  }

  const close = (v: boolean) => {
    if (running) return
    if (!v) setItems([])
    onOpenChange(v)
  }

  const uploadable = items.filter((i) => !i.error && i.stage === "ready").length
  const allDone = items.length > 0 && items.every((i) => i.error || i.stage === "done" || i.stage === "failed")

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
          <DialogDescription>PDF, Markdown or TXT, up to {formatBytes(MAX_UPLOAD_BYTES)} each. Files go straight to private storage.</DialogDescription>
        </DialogHeader>

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-4 py-8 text-center transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
            dragging ? "border-primary bg-primary/5" : "hover:bg-muted/40",
          )}
        >
          <UploadCloud className="mb-2 size-6 text-muted-foreground" aria-hidden />
          <p className="text-sm">
            <span className="font-medium">Drop files here</span> or click to browse
          </p>
          <input
            ref={inputRef}
            type="file"
            multiple
            accept={ACCEPTED.join(",")}
            className="sr-only"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files)
              e.target.value = ""
            }}
          />
        </div>

        {items.length > 0 && (
          <ul className="max-h-48 space-y-2 overflow-auto">
            {items.map((it, i) => (
              <li key={`${it.file.name}-${i}`} className="rounded-md border px-3 py-2">
                <div className="flex items-center gap-2 text-sm">
                  <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="min-w-0 flex-1 truncate">{it.file.name}</span>
                  <span className="text-xs text-muted-foreground">{formatBytes(it.file.size)}</span>
                  {it.stage === "done" && <CheckCircle2 className="size-4 text-success" aria-label="Uploaded" />}
                  {(it.stage === "failed" || it.error) && <XCircle className="size-4 text-destructive" aria-label="Failed" />}
                  {(it.stage === "uploading" || it.stage === "finalizing") && <Loader2 className="size-4 animate-spin" aria-label="Uploading" />}
                  {it.stage === "ready" && !running && (
                    <Button variant="ghost" size="icon-xs" aria-label={`Remove ${it.file.name}`} onClick={() => setItems((p) => p.filter((_, j) => j !== i))}>
                      <X />
                    </Button>
                  )}
                </div>
                {(it.stage === "uploading" || it.stage === "finalizing") && (
                  <div className="mt-2 flex items-center gap-2">
                    <Progress value={it.pct} className="h-1" />
                    <span className="w-20 text-right text-[11px] text-muted-foreground">{it.stage === "finalizing" ? "Queuing…" : `${it.pct}%`}</span>
                  </div>
                )}
                {(it.error || it.message) && <p className="mt-1 text-xs text-destructive">{it.error ?? it.message}</p>}
              </li>
            ))}
          </ul>
        )}

        <div className="grid gap-3 sm:grid-cols-3">
          <div className="grid gap-1.5">
            <Label>Type</Label>
            <Select value={sourceType} onValueChange={(v) => setSourceType(v as SourceType)} disabled={running}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="runbook">Runbook</SelectItem>
                <SelectItem value="architecture">Architecture</SelectItem>
                <SelectItem value="incident_report">Incident report</SelectItem>
                <SelectItem value="other">Other</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="up-service">Service</Label>
            <Input id="up-service" placeholder="orders-api" value={service} onChange={(e) => setService(e.target.value)} disabled={running} />
          </div>
          <div className="grid gap-1.5">
            <Label>Environment</Label>
            <Select value={environment || "none"} onValueChange={(v) => setEnvironment(v === "none" ? "" : v)} disabled={running}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Any</SelectItem>
                <SelectItem value="production">production</SelectItem>
                <SelectItem value="staging">staging</SelectItem>
                <SelectItem value="development">development</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          {allDone ? (
            <Button onClick={() => close(false)}>Done</Button>
          ) : (
            <Button onClick={start} disabled={running || uploadable === 0}>
              {running && <Loader2 className="animate-spin" />}
              Upload {uploadable > 0 ? uploadable : ""} file{uploadable === 1 ? "" : "s"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
