"use client"

import { BrainCircuit, Plus, Swords, Trash2 } from "lucide-react"
import Link from "next/link"

import { Button, buttonVariants } from "@/components/ui/button"
import type { ConversationSummary } from "@/lib/api"
import { cn } from "@/lib/utils"

interface SidebarProps {
  conversations: ConversationSummary[]
  status: "loading" | "ready" | "error"
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
}

export function Sidebar({
  conversations,
  status,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: SidebarProps) {
  return (
    // Masquée sur les petits écrans : le chat prend toute la largeur.
    <aside className="hidden w-64 shrink-0 flex-col border-r bg-card/40 md:flex">
      <div className="flex items-center gap-2 px-4 py-3 font-semibold tracking-tight">
        <BrainCircuit className="size-5 text-primary" />
        Netherbrain
      </div>
      <div className="flex flex-col gap-1 px-3 pb-2">
        <Button variant="outline" className="w-full justify-start" onClick={onNew}>
          <Plus />
          New chat
        </Button>
        {/* <Link> précharge la page en arrière-plan : la navigation est instantanée. */}
        <Link
          href="/compare"
          className={buttonVariants({ variant: "ghost", className: "w-full justify-start" })}
        >
          <Swords />
          Compare models
        </Link>
      </div>

      <nav aria-label="Conversations" className="flex-1 overflow-y-auto px-2 pb-4">
        {status === "error" ? (
          <p className="px-2 text-xs text-muted-foreground">
            History unavailable: new chats will not be saved.
          </p>
        ) : status === "ready" && conversations.length === 0 ? (
          <p className="px-2 text-xs text-muted-foreground">No conversations yet.</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {conversations.map((conversation) => {
              const title = conversation.title ?? "Untitled"
              const active = conversation.id === activeId
              return (
                <li key={conversation.id} className="group relative">
                  <button
                    type="button"
                    onClick={() => onSelect(conversation.id)}
                    aria-current={active ? "page" : undefined}
                    title={title}
                    className={cn(
                      "w-full truncate rounded-md py-1.5 pr-8 pl-2 text-left text-sm hover:bg-accent",
                      active && "bg-accent",
                    )}
                  >
                    {title}
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(conversation.id)}
                    aria-label={`Delete "${title}"`}
                    className="absolute top-1/2 right-1 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </nav>
    </aside>
  )
}
