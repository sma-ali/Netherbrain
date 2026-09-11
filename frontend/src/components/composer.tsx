"use client"

import { ArrowUp, Square } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

interface ComposerProps {
  onSend: (text: string) => void
  onStop: () => void
  streaming: boolean
  disabled: boolean
  placeholder?: string
}

export function Composer({ onSend, onStop, streaming, disabled, placeholder }: ComposerProps) {
  const [value, setValue] = useState("")
  const canSend = !disabled && !streaming && value.trim() !== ""

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
      className="relative"
    >
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
        placeholder={placeholder ?? (disabled ? "No model available" : "Ask the Netherbrain…")}
        disabled={disabled}
        rows={1}
        aria-label="Message"
        className="max-h-60 min-h-12 resize-none rounded-2xl py-3 pr-12 pl-4"
      />
      <div className="absolute right-2 bottom-2">
        {streaming ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop} aria-label="Stop">
            <Square className="fill-current" />
          </Button>
        ) : (
          <Button type="submit" size="icon" disabled={!canSend} aria-label="Send">
            <ArrowUp />
          </Button>
        )}
      </div>
    </form>
  )
}
