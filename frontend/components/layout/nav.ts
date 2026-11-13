import { BarChart3, BookOpen, LayoutDashboard, Plug, ScrollText, Search, Siren } from "lucide-react"

export const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/investigations", label: "Investigations", icon: Siren },
  { href: "/search", label: "Search", icon: Search },
  { href: "/knowledge", label: "Knowledge base", icon: BookOpen },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/evaluations", label: "Evaluations", icon: BarChart3 },
  { href: "/audit", label: "Audit log", icon: ScrollText },
] as const
