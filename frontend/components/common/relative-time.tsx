"use client"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { absoluteTime, relativeTime } from "@/lib/format"
import { cn } from "@/lib/utils"

export function RelativeTime({ iso, className }: { iso: string; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <time dateTime={iso} className={cn("cursor-default whitespace-nowrap", className)}>
          {relativeTime(iso)}
        </time>
      </TooltipTrigger>
      <TooltipContent>
        <span className="font-mono">{absoluteTime(iso)}</span>
      </TooltipContent>
    </Tooltip>
  )
}
