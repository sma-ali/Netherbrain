"use client"

import { ChevronRight, Folder, FolderGit2, Loader2, ShieldCheck } from "lucide-react"
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

/** Choisir un dossier de votre dossier personnel, l'approuver, et en faire un projet. */
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
  // Le dossier ouvert, relatif au dossier atteignable ("" : votre dossier personnel).
  const [path, setPath] = useState("")
  const [listing, setListing] = useState<DirectoryListing | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [createError, setCreateError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  // Seconde étape, comme dans Claude Code : approuver le dossier avant d'en faire un projet.
  const [confirming, setConfirming] = useState(false)

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
    setConfirming(false)
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

  if (confirming && listing) {
    return (
      <TrustStep
        folder={path ? `${listing.root.replace(/\/$/, "")}/${path}` : listing.root}
        name={name.trim() || folderName}
        creating={creating}
        error={createError}
        onBack={() => setConfirming(false)}
        onTrust={create}
      />
    )
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>Add a project</DialogTitle>
        <DialogDescription>
          Pick any folder of your home folder. Its conversations will know the project and follow
          its AGENTS.md or CLAUDE.md.
        </DialogDescription>
      </DialogHeader>

      <nav
        aria-label="Folder path"
        className="flex flex-wrap items-center gap-0.5 font-mono text-xs"
      >
        <Crumb onClick={() => navigate("")} current={path === ""}>
          ~
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
          <p className="p-3 text-muted-foreground">
            No subfolders.
          </p>
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
        <Button onClick={() => setConfirming(true)} disabled={!path || loading}>
          {folderName ? `Add “${folderName}”` : "Open a folder"}
        </Button>
      </DialogFooter>
    </>
  )
}

/** Approuver le dossier : ce que l'agent pourra y faire seul, et ce qu'il vous demandera. */
function TrustStep({
  folder,
  name,
  creating,
  error,
  onBack,
  onTrust,
}: {
  folder: string
  name: string
  creating: boolean
  error: string | null
  onBack: () => void
  onTrust: () => void
}) {
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <ShieldCheck className="size-5 text-primary" />
          Do you trust this folder?
        </DialogTitle>
        <DialogDescription className="font-mono text-xs break-all">{folder}</DialogDescription>
      </DialogHeader>

      <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm">
        <li>In “{name}”, the agent reads and searches files without asking.</li>
        <li>Writing a file, running a command or committing always asks you first.</li>
        <li>Any other folder of yours asks you first, once or for the whole conversation.</li>
        <li>Secret files (.env, ~/.ssh, ~/.config/cles) ask every time.</li>
      </ul>
      {error && <p className="text-destructive">{error}</p>}

      <DialogFooter>
        <Button variant="ghost" onClick={onBack} disabled={creating}>
          Back
        </Button>
        <Button onClick={onTrust} disabled={creating}>
          {creating && <Loader2 className="animate-spin" />}
          Trust and add
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
