"use client"

import { ArrowUp, FolderUp, Paperclip, Plus, Square } from "lucide-react"
import { useRef, useState, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Textarea } from "@/components/ui/textarea"
import { filesFromFolderInput, type PickedFile } from "@/lib/attachments"

interface ComposerProps {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
  disabled: boolean
  placeholder?: string
  /** Reçoit les fichiers choisis ; sans cette fonction, pas de bouton pour en joindre. */
  onAttach?: (files: PickedFile[]) => void
  /** Les fichiers joints en attente, affichés au-dessus du texte. */
  attachments?: ReactNode
  /** Des fichiers sont encore en cours d'envoi ou de lecture : on ne peut pas envoyer. */
  busy?: boolean
  /** D'autres boutons, sous le texte, à gauche : le mode agent, par exemple. */
  toolbar?: ReactNode
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
  toolbar,
}: ComposerProps) {
  const [value, setValue] = useState("")
  const filesInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const canSend = !disabled && !streaming && !busy && value.trim() !== ""

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
              <DropdownMenuContent className="w-44">
                <DropdownMenuItem onClick={() => filesInput.current?.click()}>
                  <Paperclip />
                  Add files
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => folderInput.current?.click()}>
                  <FolderUp />
                  Add a folder
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
                if (event.target.files) onAttach(filesFromFolderInput(event.target.files))
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
              title={busy ? "Wait until the attached files are read" : undefined}
            >
              <ArrowUp />
            </Button>
          )}
        </div>
      </div>
    </form>
  )
}
