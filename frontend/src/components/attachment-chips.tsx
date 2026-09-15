"use client"

import { FileText, Folder, LoaderCircle, TriangleAlert, X } from "lucide-react"

import {
  groupAttachments,
  groupStatus,
  type AttachmentGroup,
  type AttachmentItem,
} from "@/lib/attachments"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

interface AttachmentChipsProps {
  items: AttachmentItem[]
  /** Retire des fichiers ; sans cette fonction (message déjà envoyé), pas de croix. */
  onRemove?: (ids: string[]) => void
  className?: string
}

/** Les fichiers joints, en pastilles : une par fichier seul, une par dossier joint. */
export function AttachmentChips({ items, onRemove, className }: AttachmentChipsProps) {
  if (items.length === 0) return null
  return (
    <ul className={cn("flex flex-wrap gap-2", className)}>
      {groupAttachments(items).map((group) => (
        <Chip key={group.key} group={group} onRemove={onRemove} />
      ))}
    </ul>
  )
}

function Chip({ group, onRemove }: { group: AttachmentGroup; onRemove?: (ids: string[]) => void }) {
  const { status, errors } = groupStatus(group.items)
  const failed = errors > 0 && errors === group.items.length
  const size = group.items.reduce((total, item) => total + item.size, 0)
  const Icon = group.folder ? Folder : FileText

  const detail =
    status === "uploading"
      ? "Uploading…"
      : status === "processing"
        ? "Reading…"
        : failed && !group.folder
          ? (group.items[0].error ?? "Unreadable")
          : errors > 0
            ? `${errors} of ${group.items.length} files unreadable`
            : group.folder
              ? `${group.items.length} files · ${formatBytes(size)}`
              : formatBytes(size)

  // Au survol : le détail de chaque erreur.
  const title = [
    group.label,
    ...group.items
      .filter((item) => item.error)
      .map((item) => `${item.path ?? item.name}: ${item.error}`),
  ].join("\n")

  return (
    <li
      title={title}
      className={cn(
        "flex max-w-72 items-center gap-2 rounded-lg border bg-background/60 py-1.5 pr-1.5 pl-2.5 text-xs",
        errors > 0 && "border-destructive/50",
      )}
    >
      {status !== "ready" ? (
        <LoaderCircle className="size-4 shrink-0 animate-spin text-muted-foreground" />
      ) : failed ? (
        <TriangleAlert className="size-4 shrink-0 text-destructive" />
      ) : (
        <Icon className="size-4 shrink-0 text-primary" />
      )}
      <span className="min-w-0">
        <span className="block truncate font-medium">{group.label}</span>
        <span
          className={cn("block truncate text-muted-foreground", errors > 0 && "text-destructive")}
        >
          {detail}
        </span>
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(group.items.map((item) => item.id))}
          aria-label={`Remove ${group.label}`}
          className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      )}
    </li>
  )
}
