"use client"

import { ArrowUp, FolderUp, Paperclip, Plus, Square, X } from "lucide-react"
import { useRef, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Textarea } from "@/components/ui/textarea"
import { filesFromFolderInput, MAX_FILES, type PickedFile } from "@/lib/attachments"
import { cn } from "@/lib/utils"

interface ComposerProps {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
  disabled: boolean
  placeholder?: string
  /**
   * Reçoit les fichiers choisis, et le nombre de fichiers du dossier avant tri quand on le
   * connaît ; sans cette fonction, pas de bouton pour en joindre.
   */
  onAttach?: (files: PickedFile[], total?: number) => void
  /** Les fichiers joints en attente, affichés au-dessus du texte. */
  attachments?: ReactNode
  /** Des fichiers sont encore en cours d'envoi ou de lecture : on ne peut pas envoyer. */
  busy?: boolean
  /** Ce qui empêche d'envoyer (des images pour un modèle qui ne les lit pas), affiché tel quel. */
  blocked?: string | null
  /** Des remarques sous les fichiers joints, qui n'empêchent pas d'envoyer (voir ComposerNotice). */
  notices?: ReactNode
  /** D'autres boutons, sous le texte, à gauche : le mode agent, par exemple. */
  toolbar?: ReactNode
  /** Le texte déjà saisi à l'ouverture (une demande reprise d'une autre page). */
  initialValue?: string
}

export function Composer({
  onSend,
  onStop,
  streaming,
  disabled,
  placeholder,
  onAttach,
  attachments,
  busy = false,
  blocked = null,
  notices,
  toolbar,
  initialValue = "",
}: ComposerProps) {
  const [value, setValue] = useState(initialValue)
  const filesInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const canSend = !disabled && !streaming && !busy && !blocked && value.trim() !== ""

  const submit = () => {
    if (!canSend) return
    onSend(value.trim())
    setValue("")
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
      className="rounded-2xl border bg-card/60 transition-colors focus-within:border-ring"
    >
      {attachments && <div className="px-3 pt-3">{attachments}</div>}
      {blocked && (
        <p role="status" className="px-4 pt-2 text-xs text-amber-600 dark:text-amber-400">
          {blocked}
        </p>
      )}
      {notices}
      <Textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          // Entrée envoie, Maj+Entrée ajoute une ligne. isComposing : ignore une saisie
          // encore en cours de composition (claviers japonais, chinois…).
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault()
            submit()
          }
        }}
        onPaste={(event) => {
          // Coller un fichier copié (ou une capture d'écran) le joint au message.
          const files = Array.from(event.clipboardData.files)
          if (!onAttach || files.length === 0) return
          event.preventDefault()
          onAttach(files.map((file) => ({ file })))
        }}
        placeholder={placeholder ?? (disabled ? "No model available" : "Ask the Netherbrain…")}
        disabled={disabled}
        rows={1}
        aria-label="Message"
        className="max-h-60 min-h-12 resize-none border-0 bg-transparent px-4 py-3 shadow-none focus-visible:ring-0 dark:bg-transparent"
      />
      <div className="flex items-center gap-1.5 px-2 pb-2">
        {onAttach && (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Attach files or a folder"
                    disabled={disabled}
                  />
                }
              >
                <Plus />
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-60">
                <DropdownMenuItem onClick={() => filesInput.current?.click()}>
                  <Paperclip />
                  <MenuLabel hint="Read-only copies for the model">Add files</MenuLabel>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => folderInput.current?.click()}>
                  <FolderUp />
                  <MenuLabel hint={`Read-only copies, up to ${MAX_FILES} files`}>
                    Add a folder
                  </MenuLabel>
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <input
              ref={filesInput}
              type="file"
              multiple
              hidden
              onChange={(event) => {
                const files = Array.from(event.target.files ?? [])
                if (files.length > 0) onAttach(files.map((file) => ({ file })))
                // Permet de rejoindre le même fichier juste après.
                event.target.value = ""
              }}
            />
            <input
              ref={folderInput}
              type="file"
              hidden
              // Choisir un dossier entier : l'attribut n'est pas dans les types de React.
              {...{ webkitdirectory: "" }}
              onChange={(event) => {
                const files = event.target.files
                if (files) onAttach(filesFromFolderInput(files), files.length)
                event.target.value = ""
              }}
            />
          </>
        )}
        {toolbar}
        <div className="ml-auto">
          {streaming ? (
            <Button
              type="button"
              size="icon"
              variant="secondary"
              onClick={onStop}
              aria-label="Stop"
            >
              <Square className="fill-current" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              disabled={!canSend}
              aria-label="Send"
              title={blocked ?? (busy ? "Wait until the attached files are read" : undefined)}
            >
              <ArrowUp />
            </Button>
          )}
        </div>
      </div>
    </form>
  )
}

function MenuLabel({ children, hint }: { children: ReactNode; hint: string }) {
  return (
    <span className="flex flex-col">
      {children}
      <span className="text-xs text-muted-foreground">{hint}</span>
    </span>
  )
}

interface ComposerNoticeProps {
  children: ReactNode
  /** warning : ce qui empêche d'obtenir ce qu'on attend ; info : un simple rappel. */
  tone?: "info" | "warning"
  /** Un bouton qui règle le problème d'un clic. */
  action?: ReactNode
  onDismiss?: () => void
}

/** Une remarque sous les fichiers joints : ce qui risque de ne pas marcher, et comment faire. */
export function ComposerNotice({
  children,
  tone = "info",
  action,
  onDismiss,
}: ComposerNoticeProps) {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-wrap items-center gap-x-3 gap-y-1 px-4 pt-2 text-xs",
        tone === "warning" ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground",
      )}
    >
      <span className="min-w-0 flex-1">{children}</span>
      {action}
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss"
          className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  )
}
