"use client"

import { Loader2 } from "lucide-react"
import { useRouter } from "next/navigation"
import { useEffect, type ReactNode } from "react"
import { MockBanner } from "@/components/common/mock-banner"
import { SidebarContent } from "@/components/layout/sidebar"
import { Topbar } from "@/components/layout/topbar"
import { useAuth } from "@/lib/auth/auth-provider"

export default function AppLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (status === "anonymous") router.replace("/login")
  }, [status, router])

  if (status !== "authenticated") {
    return (
      <div className="flex min-h-svh items-center justify-center" aria-busy="true">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Loading" />
      </div>
    )
  }

  return (
    <div className="flex min-h-svh flex-col">
      <div className="flex flex-1">
        <aside className="no-print sticky top-0 hidden h-svh w-60 shrink-0 border-r bg-sidebar md:block">
          <SidebarContent />
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <MockBanner />
          <Topbar />
          <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6">{children}</main>
        </div>
      </div>
    </div>
  )
}
