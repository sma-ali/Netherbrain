"use client"

import { FileText, LoaderCircle, Trash2, Upload } from "lucide-react"
import { useEffect, useState } from "react"

import { AppNav } from "@/components/app-nav"
import { Sidebar } from "@/components/sidebar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useSavedList } from "@/hooks/use-saved-list"
import { deleteDocument, listDocuments, uploadDocument, type DocumentInfo } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"

const ACCEPTED = ".pdf,.txt,.md,.markdown"

export function DocumentsLibrary() {
  const documents = useSavedList(listDocuments, deleteDocument)
  const { refresh } = documents
  const [uploading, setUploading] = useState<string[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [dragging, setDragging] = useState(false)

  const indexing = documents.items.some((doc) => doc.status === "processing")

  // Tant qu'un document est en cours d'indexation, on redemande les statuts toutes les
  // 2 secondes (« polling ») : plus simple qu'un canal temps réel, et suffisant ici.
  useEffect(() => {
    if (!indexing) return
    const timer = setInterval(refresh, 2000)
    return () => clearInterval(timer)
  }, [indexing, refresh])

  const upload = async (files: FileList) => {
    setErrors([])
    for (const file of Array.from(files)) {
      setUploading((prev) => [...prev, file.name])
      try {
        await uploadDocument(file)
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        setErrors((prev) => [...prev, `${file.name}: ${message}`])
      } finally {
        setUploading((prev) => prev.filter((name) => name !== file.name))
        refresh()
      }
    }
  }

  const handleDelete = async (doc: DocumentInfo) => {
    if (!window.confirm(`Delete "${doc.name}"?`)) return
    try {
      await documents.remove(doc.id)
    } catch (error) {
      window.alert(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <div className="flex h-dvh">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b px-4 py-2.5">
          <AppNav compact className="md:hidden" />
          <h1 className="font-semibold tracking-tight">Documents</h1>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-6">
            <p className="text-sm text-muted-foreground">
              Import PDF, text or Markdown files, then turn on “Use my documents” in the chat:
              the model answers from them and cites its sources. With a local model, nothing
              leaves your machine.
            </p>

            <label
              onDragOver={(event) => {
                event.preventDefault()
                setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                void upload(event.dataTransfer.files)
              }}
              className={cn(
                "flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors hover:bg-accent/40",
                dragging && "border-primary bg-primary/10",
              )}
            >
              <Upload className="size-8 text-primary" />
              <span className="text-sm font-medium">Drop files here, or click to choose</span>
              <span className="text-xs text-muted-foreground">PDF, TXT or Markdown · up to 20 MB</span>
              <input
                type="file"
                accept={ACCEPTED}
                multiple
                className="sr-only"
                onChange={(event) => {
                  if (event.target.files) void upload(event.target.files)
                  // Permet de réimporter le même fichier juste après.
                  event.target.value = ""
                }}
              />
            </label>

            {uploading.length > 0 && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                Uploading {uploading.join(", ")}…
              </p>
            )}
            {errors.map((error) => (
              <p key={error} className="text-sm text-destructive">
                {error}
              </p>
            ))}

            {documents.status === "error" ? (
              <p className="text-sm text-destructive">
                Documents unavailable: the database cannot be reached.
              </p>
            ) : documents.status === "ready" && documents.items.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground">No documents yet.</p>
            ) : (
              <ul className="flex flex-col divide-y rounded-xl border">
                {documents.items.map((doc) => (
                  <DocumentRow key={doc.id} doc={doc} onDelete={() => handleDelete(doc)} />
                ))}
              </ul>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function DocumentRow({ doc, onDelete }: { doc: DocumentInfo; onDelete: () => void }) {
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <FileText className="size-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium" title={doc.name}>
          {doc.name}
        </p>
        <p className="text-xs text-muted-foreground">
          {formatBytes(doc.size_bytes)}
          {doc.status === "ready" && ` · ${doc.chunk_count} chunks`}
        </p>
        {doc.status === "error" && doc.error && (
          <p className="text-xs text-destructive">{doc.error}</p>
        )}
      </div>
      <StatusBadge status={doc.status} />
      <Button variant="ghost" size="icon" onClick={onDelete} aria-label={`Delete ${doc.name}`}>
        <Trash2 />
      </Button>
    </li>
  )
}

function StatusBadge({ status }: { status: DocumentInfo["status"] }) {
  if (status === "processing") {
    return (
      <Badge variant="outline">
        <LoaderCircle className="animate-spin" />
        Indexing…
      </Badge>
    )
  }
  return (
    <Badge variant={status === "ready" ? "secondary" : "destructive"}>
      {status === "ready" ? "Ready" : "Error"}
    </Badge>
  )
}
