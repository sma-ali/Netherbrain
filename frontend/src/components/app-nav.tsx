"use client"

import { LayoutGrid, MessageSquare, Swords } from "lucide-react"
import Link from "next/link"
import { usePathname } from "next/navigation"

import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const LINKS = [
  { href: "/", label: "Chat", icon: MessageSquare },
  { href: "/compare", label: "Compare", icon: Swords },
  { href: "/models", label: "Models", icon: LayoutGrid },
]

/**
 * La navigation entre les pages. `compact` : des icônes seules, pour les petits écrans.
 * <Link> précharge les pages en arrière-plan : la navigation est instantanée.
 */
export function AppNav({ compact = false, className }: { compact?: boolean; className?: string }) {
  const pathname = usePathname()

  return (
    <nav aria-label="Main" className={cn("flex", compact ? "gap-1" : "flex-col gap-0.5", className)}>
      {LINKS.map(({ href, label, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            aria-label={compact ? label : undefined}
            title={compact ? label : undefined}
            className={buttonVariants({
              variant: active ? "secondary" : "ghost",
              size: compact ? "icon" : "default",
              className: compact ? undefined : "w-full justify-start",
            })}
          >
            <Icon />
            {!compact && label}
          </Link>
        )
      })}
    </nav>
  )
}
