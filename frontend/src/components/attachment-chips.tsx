"use client"

import { FileText, Folder, LoaderCircle, TriangleAlert, X } from "lucide-react"

import { attachmentUrl } from "@/lib/api"
import {
  groupAttachments,
  groupStatus,
  isImage,
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
  /** Des images en grand : dans un message envoyé, plutôt qu'en vignette dans la saisie. */
  large?: boolean
}

/** Les fichiers joints : les images en vignettes, les autres en pastilles (une par dossier). */
export function AttachmentChips({
  items,
  onRemove,
  className,
  large = false,
}: AttachmentChipsProps) {
  if (items.length === 0) return null
  return (
    <ul className={cn("flex flex-wrap gap-2", className)}>
      {items.filter(isImage).map((item) => (
        <ImageThumbnail key={item.id} item={item} onRemove={onRemove} large={large} />
      ))}
      {groupAttachments(items.filter((item) => !isImage(item))).map((group) => (
        <Chip key={group.key} group={group} onRemove={onRemove} />
      ))}
    </ul>
  )
}

interface ImageThumbnailProps {
  item: AttachmentItem
  onRemove?: (ids: string[]) => void
  large: boolean
}

function ImageThumbnail({ item, onRemove, large }: ImageThumbnailProps) {
  const failed = item.status === "error"
  // L'adresse n'existe qu'une fois l'image enregistrée par le serveur.
  const url =
    item.conversationId && item.status === "ready"
      ? attachmentUrl(item.conversationId, item.id)
      : null

  return (
    <li
      title={failed ? `${item.name}: ${item.error ?? "Unreadable"}` : item.name}
      className={cn(
        "relative overflow-hidden rounded-lg border bg-muted/40",
        failed && "border-destructive/50",
      )}
    >
      {url ? (
        // Un lien vers l'original : la vignette peut être rognée.
        <a href={url} target="_blank" rel="noreferrer" className="block">
          {/* eslint-disable-next-line @next/next/no-img-element -- servie par l'API, que next/image ne peut pas optimiser */}
          <img
            src={url}
            alt={item.name}
            className={cn(
              "block",
              large ? "max-h-48 max-w-64 object-contain" : "size-16 object-cover",
            )}
          />
        </a>
      ) : (
        <span className="flex size-16 items-center justify-center">
          {failed ? (
            <TriangleAlert className="size-5 text-destructive" />
          ) : (
            <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
          )}
        </span>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove([item.id])}
          aria-label={`Remove ${item.name}`}
          className="absolute top-1 right-1 rounded-full bg-background/85 p-0.5 text-muted-foreground hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      )}
    </li>
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
