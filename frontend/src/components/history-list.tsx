"use client"

import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export interface HistoryItem {
  id: string
  title: string
  subtitle?: string
}

interface HistoryListProps {
  items: HistoryItem[]
  status: "loading" | "ready" | "error"
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  newLabel: string
  emptyLabel: string
}

/** L'historique d'une page (conversations ou comparaisons) : ouvrir, créer, supprimer. */
export function HistoryList({
  items,
  status,
  activeId,
  onSelect,
  onNew,
  onDelete,
  newLabel,
  emptyLabel,
}: HistoryListProps) {
  return (
    <>
      <div className="border-t px-3 pt-3 pb-2">
        <Button variant="outline" className="w-full justify-start" onClick={onNew}>
          <Plus />
          {newLabel}
        </Button>
      </div>

      <nav aria-label="History" className="flex-1 overflow-y-auto px-2 pb-4">
        {status === "error" ? (
          <HistoryUnavailable />
        ) : status === "ready" && items.length === 0 ? (
          <p className="px-2 text-xs text-muted-foreground">{emptyLabel}</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {items.map((item) => (
              <HistoryRow
                key={item.id}
                item={item}
                active={item.id === activeId}
                onSelect={onSelect}
                onDelete={onDelete}
              />
            ))}
          </ul>
        )}
      </nav>
    </>
  )
}

export function HistoryUnavailable() {
  return (
    <p className="px-2 text-xs text-muted-foreground">
      History unavailable: nothing new will be saved.
    </p>
  )
}

interface HistoryRowProps {
  item: HistoryItem
  active: boolean
  onSelect: (id: string) => void
  onDelete: (id: string) => void
}

/** Une ligne de l'historique : cliquer l'ouvre, la corbeille (visible au survol) la supprime. */
export function HistoryRow({ item, active, onSelect, onDelete }: HistoryRowProps) {
  return (
    <li className="group relative">
      <button
        type="button"
        onClick={() => onSelect(item.id)}
        aria-current={active ? "page" : undefined}
        title={item.title}
        className={cn(
          "flex w-full flex-col rounded-md py-1.5 pr-8 pl-2 text-left hover:bg-accent",
          active && "bg-accent",
        )}
      >
        <span className="truncate text-sm">{item.title}</span>
        {item.subtitle && (
          <span className="truncate text-xs text-muted-foreground">{item.subtitle}</span>
        )}
      </button>
      <button
        type="button"
        onClick={() => onDelete(item.id)}
        aria-label={`Delete "${item.title}"`}
        className="absolute top-1/2 right-1 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-destructive focus-visible:opacity-100"
      >
        <Trash2 className="size-3.5" />
      </button>
    </li>
  )
}
