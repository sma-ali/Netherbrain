"use client"

import { ChevronRight, Folder, FolderGit2, Loader2 } from "lucide-react"
import { Fragment, useEffect, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { createProject, listDirectories, type DirectoryListing, type Project } from "@/lib/api"
import { basename, breadcrumbs } from "@/lib/projects"

interface AddProjectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: (project: Project) => void
}

/** Choisir un dossier du dossier de travail, et en faire un projet. */
export function AddProjectDialog({ open, onOpenChange, onCreated }: AddProjectDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        {/* La fenêtre est démontée à la fermeture : on repart de la racine à chaque ouverture. */}
        <FolderBrowser onCreated={onCreated} />
      </DialogContent>
    </Dialog>
  )
}

function FolderBrowser({ onCreated }: { onCreated: (project: Project) => void }) {
  // Le dossier ouvert, relatif au dossier de travail ("" : la racine).
  const [path, setPath] = useState("")
  const [listing, setListing] = useState<DirectoryListing | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [createError, setCreateError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    listDirectories(path, controller.signal)
      .then(setListing)
      .catch((error) => {
        if (!controller.signal.aborted) setListError(errorText(error))
      })
    // Un clic sur un autre dossier annule la requête en cours : pas de réponse périmée.
    return () => controller.abort()
  }, [path])

  // État dérivé : on charge tant que la liste affichée n'est pas celle du dossier demandé.
  const loading = listError === null && listing?.path !== path
  const folderName = path ? basename(path) : ""

  const navigate = (next: string) => {
    setPath(next)
    setName("")
    setListError(null)
    setCreateError(null)
  }

  const create = async () => {
    setCreating(true)
    setCreateError(null)
    try {
      onCreated(await createProject(path, name.trim()))
    } catch (error) {
      setCreateError(errorText(error))
      setCreating(false)
    }
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Add a project</DialogTitle>
        <DialogDescription>
          Pick a folder in your workspace. Its conversations will know the project and follow
          its AGENTS.md or CLAUDE.md.
        </DialogDescription>
      </DialogHeader>

      <nav aria-label="Folder path" className="flex flex-wrap items-center gap-0.5 font-mono text-xs">
        <Crumb onClick={() => navigate("")} current={path === ""}>
          {listing ? basename(listing.root) : "workspace"}
        </Crumb>
        {breadcrumbs(path).map((crumb) => (
          <Fragment key={crumb.path}>
            <ChevronRight className="size-3 text-muted-foreground" />
            <Crumb onClick={() => navigate(crumb.path)} current={crumb.path === path}>
              {crumb.name}
            </Crumb>
          </Fragment>
        ))}
      </nav>

      <div className="h-64 overflow-y-auto rounded-lg border">
        {listError ? (
          <p className="p-3 text-destructive">{listError}</p>
        ) : loading || !listing ? (
          <p className="flex items-center gap-2 p-3 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading…
          </p>
        ) : listing.directories.length === 0 ? (
          <p className="p-3 text-muted-foreground">No subfolders.</p>
        ) : (
          <ul className="p-1">
            {listing.directories.map((folder) => (
              <li key={folder.path}>
                <button
                  type="button"
                  onClick={() => navigate(folder.path)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-accent"
                >
                  {folder.is_git ? (
                    <FolderGit2 className="size-4 shrink-0 text-primary" />
                  ) : (
                    <Folder className="size-4 shrink-0 text-muted-foreground" />
                  )}
                  <span className="truncate">{folder.name}</span>
                  <ChevronRight className="ml-auto size-4 shrink-0 text-muted-foreground" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <label className="flex flex-col gap-1.5">
        Project name
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={folderName || "Open a folder first"}
          disabled={!path}
          maxLength={200}
        />
      </label>
      {createError && <p className="text-destructive">{createError}</p>}

      <DialogFooter>
        <Button onClick={create} disabled={!path || loading || creating}>
          {creating && <Loader2 className="animate-spin" />}
          {folderName ? `Add “${folderName}”` : "Open a folder"}
        </Button>
      </DialogFooter>
    </>
  )
}

function Crumb({
  onClick,
  current,
  children,
}: {
  onClick: () => void
  current: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={current ? "location" : undefined}
      className="rounded px-1 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground aria-[current]:text-foreground"
    >
      {children}
    </button>
  )
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
