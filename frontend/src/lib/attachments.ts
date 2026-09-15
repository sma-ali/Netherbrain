/** Joindre des fichiers au chat : les choisir, écarter le superflu, les regrouper pour l'affichage. */

import type { AttachmentInfo } from "@/lib/api"

/** Un fichier choisi par l'utilisateur, avec son chemin s'il vient d'un dossier. */
export interface PickedFile {
  file: File
  // Chemin dans le dossier joint (« app/src/main.py ») ; absent pour un fichier seul.
  path?: string
}

/** Un fichier dans la zone de saisie, ou déjà envoyé avec un message. */
export interface AttachmentItem {
  // Identifiant local pendant l'envoi, puis celui du serveur.
  id: string
  name: string
  path: string | null
  size: number
  // uploading : envoi en cours ; processing : le serveur lit le fichier.
  status: "uploading" | "processing" | "ready" | "error"
  error?: string | null
}

// Dossiers qu'on ne joint jamais : dépendances, caches et sorties de build, souvent énormes.
const IGNORED_FOLDERS = new Set([
  "node_modules",
  "__pycache__",
  "venv",
  "dist",
  "build",
  "target",
  "coverage",
])

/** Au-delà, les fichiers suivants d'un dossier sont ignorés. */
export const MAX_FILES = 200

/** Un fichier de dossier à écarter : caché (.git, .env…) ou dans un dossier de dépendances. */
export function isIgnored(path: string): boolean {
  return path.split("/").some((part) => part.startsWith(".") || IGNORED_FOLDERS.has(part))
}

/** Les fichiers choisis avec « Add a folder » : leur chemin est dans `webkitRelativePath`. */
export function filesFromFolderInput(files: FileList | File[]): PickedFile[] {
  return Array.from(files)
    .map((file) => ({ file, path: file.webkitRelativePath || file.name }))
    .filter(({ path }) => !isIgnored(path))
    .slice(0, MAX_FILES)
}

/** Les fichiers déposés par glisser-déposer, dossiers compris (parcourus récursivement). */
export async function filesFromDrop(dataTransfer: DataTransfer): Promise<PickedFile[]> {
  // À lire tout de suite : le navigateur vide `dataTransfer` dès la fin de l'événement.
  const entries = Array.from(dataTransfer.items)
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is FileSystemEntry => entry !== null)
  if (entries.length === 0) return Array.from(dataTransfer.files).map((file) => ({ file }))

  const picked: PickedFile[] = []
  for (const entry of entries) await collect(entry, picked, false)
  return picked
}

async function collect(entry: FileSystemEntry, picked: PickedFile[], inFolder: boolean) {
  if (picked.length >= MAX_FILES) return
  const path = entry.fullPath.replace(/^\//, "")

  if (entry.isFile) {
    if (inFolder && isIgnored(path)) return
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject),
    )
    picked.push(inFolder ? { file, path } : { file })
  } else if (entry.isDirectory && !isIgnored(path)) {
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    // readEntries rend le contenu par paquets : on relit jusqu'à recevoir un paquet vide.
    let batch: FileSystemEntry[]
    do {
      batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
        reader.readEntries(resolve, reject),
      )
      for (const child of batch) await collect(child, picked, true)
    } while (batch.length > 0)
  }
}

export interface AttachmentGroup {
  key: string
  // Le nom du dossier, ou celui du fichier seul.
  label: string
  folder: boolean
  items: AttachmentItem[]
}

/** Regroupe les fichiers d'un même dossier : une seule pastille « app · 23 files ». */
export function groupAttachments(items: AttachmentItem[]): AttachmentGroup[] {
  const groups: AttachmentGroup[] = []
  const folders = new Map<string, AttachmentGroup>()
  for (const item of items) {
    const folder = item.path?.includes("/") ? item.path.split("/")[0] : null
    if (folder === null) {
      groups.push({ key: item.id, label: item.name, folder: false, items: [item] })
      continue
    }
    let group = folders.get(folder)
    if (!group) {
      group = { key: `folder:${folder}`, label: folder, folder: true, items: [] }
      folders.set(folder, group)
      groups.push(group)
    }
    group.items.push(item)
  }
  return groups
}

/** L'état d'un groupe : en cours tant qu'un de ses fichiers l'est, et combien sont illisibles. */
export function groupStatus(items: AttachmentItem[]): {
  status: "uploading" | "processing" | "ready"
  errors: number
} {
  const errors = items.filter((item) => item.status === "error").length
  const status = items.some((item) => item.status === "uploading")
    ? "uploading"
    : items.some((item) => item.status === "processing")
      ? "processing"
      : "ready"
  return { status, errors }
}

/** Lance les tâches `size` à la fois : assez pour aller vite, sans saturer le serveur. */
export async function runPool(tasks: (() => Promise<void>)[], size: number): Promise<void> {
  let next = 0
  const worker = async () => {
    while (next < tasks.length) {
      const task = tasks[next]
      next += 1
      await task()
    }
  }
  await Promise.all(Array.from({ length: Math.min(size, tasks.length) }, worker))
}

export function fromAttachmentInfo(attachment: AttachmentInfo): AttachmentItem {
  return {
    id: attachment.id,
    name: attachment.name,
    path: attachment.path,
    size: attachment.size_bytes,
    status: attachment.status,
    error: attachment.error,
  }
}
