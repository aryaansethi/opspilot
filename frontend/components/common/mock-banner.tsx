import { FlaskConical } from "lucide-react"
import { IS_MOCK } from "@/lib/api/config"

/** Makes it impossible to mistake sample data for real results. */
export function MockBanner() {
  if (!IS_MOCK) return null
  return (
    <div className="flex items-center justify-center gap-2 border-b border-warning/30 bg-warning/10 px-4 py-1.5 text-xs text-warning">
      <FlaskConical className="size-3.5" aria-hidden />
      Mock mode — sample data only, not connected to a backend. Nothing here is a real measurement.
    </div>
  )
}
