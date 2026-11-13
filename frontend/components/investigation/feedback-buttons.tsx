"use client"

import { ThumbsDown, ThumbsUp } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { errorMessage } from "@/lib/api/client"
import { useSendFeedback } from "@/lib/api/endpoints/feedback"
import type { FeedbackRequest } from "@/lib/types/api"

export function FeedbackButtons({ targetType, targetId }: { targetType: FeedbackRequest["target_type"]; targetId: string }) {
  const send = useSendFeedback()
  const [rating, setRating] = useState<"up" | "down" | null>(null)
  const rate = async (r: "up" | "down") => {
    try {
      await send.mutateAsync({ target_type: targetType, target_id: targetId, rating: r })
      setRating(r)
      toast.success("Thanks — feedback recorded")
    } catch (e) {
      toast.error(errorMessage(e))
    }
  }
  return (
    <div className="flex items-center gap-1 text-xs text-muted-foreground">
      Was this useful?
      <Button variant={rating === "up" ? "secondary" : "ghost"} size="icon-sm" aria-label="Useful" aria-pressed={rating === "up"} onClick={() => rate("up")} disabled={send.isPending}>
        <ThumbsUp />
      </Button>
      <Button variant={rating === "down" ? "secondary" : "ghost"} size="icon-sm" aria-label="Not useful" aria-pressed={rating === "down"} onClick={() => rate("down")} disabled={send.isPending}>
        <ThumbsDown />
      </Button>
    </div>
  )
}
