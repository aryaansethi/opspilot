"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, type ReactNode } from "react"
import { MockBanner } from "@/components/common/mock-banner"
import { Logo } from "@/components/layout/logo"
import { useAuth } from "@/lib/auth/auth-provider"

export function AuthShell({ title, subtitle, children, footer }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode }) {
  const { status } = useAuth()
  const router = useRouter()
  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard")
  }, [status, router])

  return (
    <div className="flex min-h-svh flex-col">
      <MockBanner />
      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <Link href="/" className="mb-8 inline-block">
            <Logo />
          </Link>
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 mb-6 text-sm text-muted-foreground">{subtitle}</p>
          {children}
          <p className="mt-6 text-sm text-muted-foreground">{footer}</p>
        </div>
      </div>
    </div>
  )
}
