"use client"

import { LogOut, Moon, Sun } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTheme } from "next-themes"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { usePendingApprovals } from "@/lib/api/endpoints/approvals"
import { useAuth } from "@/lib/auth/auth-provider"
import { cn } from "@/lib/utils"
import { Logo } from "./logo"
import { NAV } from "./nav"
import { WorkspaceSwitcher } from "./workspace-switcher"

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const { theme, setTheme } = useTheme()
  const pending = usePendingApprovals()
  const pendingCount = pending.data?.length ?? 0

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      <Link href="/dashboard" onClick={onNavigate} className="px-2 py-1.5">
        <Logo />
      </Link>
      <WorkspaceSwitcher />
      <nav aria-label="Main" className="mt-2 flex flex-col gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(`${href}/`)
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex h-8 items-center gap-2.5 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                active && "bg-sidebar-accent font-medium text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden />
              <span className="flex-1">{label}</span>
              {href === "/investigations" && pendingCount > 0 && (
                <span className="rounded bg-warning/15 px-1.5 text-[10px] font-semibold text-warning" title="Pending approvals">
                  {pendingCount}
                </span>
              )}
            </Link>
          )
        })}
      </nav>
      <div className="mt-auto">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-10 w-full justify-start gap-2 px-2">
              <Avatar className="size-6">
                <AvatarFallback className="text-[10px]">{user?.display_name.slice(0, 2).toUpperCase()}</AvatarFallback>
              </Avatar>
              <span className="min-w-0 text-left">
                <span className="block truncate text-sm">{user?.display_name}</span>
                <span className="block truncate text-xs text-muted-foreground">{user?.email}</span>
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-56">
            <DropdownMenuLabel className="truncate text-xs text-muted-foreground">{user?.email}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setTheme(theme === "dark" ? "light" : "dark")}>
              {theme === "dark" ? <Sun className="size-3.5" /> : <Moon className="size-3.5" />}
              {theme === "dark" ? "Light theme" : "Dark theme"}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => void logout()}>
              <LogOut className="size-3.5" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  )
}
