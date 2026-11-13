"use client"

import { ChevronRight, Menu, Moon, Search, Sun } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTheme } from "next-themes"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet"
import { CommandMenu } from "./command-menu"
import { NAV } from "./nav"
import { SidebarContent } from "./sidebar"

function useCrumbs() {
  const pathname = usePathname()
  const parts = pathname.split("/").filter(Boolean)
  return parts.map((p, i) => {
    const href = `/${parts.slice(0, i + 1).join("/")}`
    const nav = NAV.find((n) => n.href === href)
    const label = nav?.label ?? (p === "new" ? "New" : p === "report" ? "Report" : p.length > 14 ? `${p.slice(0, 8)}…` : p)
    return { href, label, last: i === parts.length - 1 }
  })
}

export function Topbar() {
  const crumbs = useCrumbs()
  const { theme, setTheme } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [cmdOpen, setCmdOpen] = useState(false)

  return (
    <header className="no-print sticky top-0 z-20 flex h-12 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur">
      <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label="Open navigation" onClick={() => setMobileOpen(true)}>
        <Menu />
      </Button>
      <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-sm">
        {crumbs.map((c) => (
          <span key={c.href} className="flex min-w-0 items-center gap-1">
            {c.last ? (
              <span className="truncate font-medium" aria-current="page">
                {c.label}
              </span>
            ) : (
              <>
                <Link href={c.href} className="truncate text-muted-foreground hover:text-foreground">
                  {c.label}
                </Link>
                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              </>
            )}
          </span>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-1">
        <Button variant="outline" size="sm" className="hidden gap-2 text-muted-foreground sm:inline-flex" onClick={() => setCmdOpen(true)}>
          <Search className="size-3.5" /> Jump to…
          <kbd className="rounded border bg-muted px-1 font-mono text-[10px]">⌘K</kbd>
        </Button>
        <Button variant="ghost" size="icon-sm" className="sm:hidden" aria-label="Open command menu" onClick={() => setCmdOpen(true)}>
          <Search />
        </Button>
        <Button variant="ghost" size="icon-sm" aria-label="Toggle theme" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
          <Sun className="hidden dark:block" />
          <Moon className="dark:hidden" />
        </Button>
      </div>
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-72 bg-sidebar p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SidebarContent onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>
      <CommandMenu open={cmdOpen} onOpenChange={setCmdOpen} />
    </header>
  )
}
