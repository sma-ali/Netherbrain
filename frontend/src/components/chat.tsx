"use client"

import { BrainCircuit, RotateCw, SquarePen } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Composer } from "@/components/composer"
import { Message } from "@/components/message"
import { ModelPicker } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { useChat } from "@/hooks/use-chat"
import { useModels } from "@/hooks/use-models"
import { modelKey, type ProviderStatus } from "@/lib/api"

export function Chat() {
  const { messages, status, send, stop, reset } = useChat()
  const models = useModels()
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  // État dérivé : on prend le premier modèle (les locaux sont en tête) tant que l'utilisateur
  // n'en a pas choisi un.
  const model =
    models.models.find((m) => modelKey(m) === selectedKey) ?? models.models[0] ?? null

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  // Suit la réponse pendant qu'elle s'affiche, sauf si l'utilisateur est remonté pour lire.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages])

  const handleScroll = () => {
    const el = scrollRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const streaming = status === "streaming"

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-2.5">
        <div className="flex items-center gap-2 font-semibold tracking-tight">
          <BrainCircuit className="size-5 text-primary" />
          Netherbrain
        </div>
        <div className="ml-auto flex items-center gap-2">
          <ModelPicker
            models={models.models}
            providers={models.providers}
            value={model ? modelKey(model) : null}
            onChange={setSelectedKey}
            loading={models.status === "loading"}
            disabled={streaming}
          />
          <Button
            variant="ghost"
            size="icon"
            onClick={reset}
            disabled={messages.length === 0}
            aria-label="New chat"
          >
            <SquarePen />
          </Button>
        </div>
      </header>

      <main ref={scrollRef} onScroll={handleScroll} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
          {messages.length === 0 ? (
            <EmptyState
              error={models.error}
              ready={models.status === "ready"}
              hasModels={models.models.length > 0}
              unavailable={models.providers.filter((p) => !p.available)}
              onRetry={models.retry}
            />
          ) : (
            messages.map((message, index) => (
              <Message
                key={message.id}
                message={message}
                streaming={streaming && index === messages.length - 1}
              />
            ))
          )}
        </div>
      </main>

      <footer className="mx-auto w-full max-w-3xl px-4 pb-4">
        <Composer
          onSend={(text) => model && send(text, model)}
          onStop={stop}
          streaming={streaming}
          disabled={!model}
        />
      </footer>
    </div>
  )
}

interface EmptyStateProps {
  error: string | null
  ready: boolean
  hasModels: boolean
  unavailable: ProviderStatus[]
  onRetry: () => void
}

function EmptyState({ error, ready, hasModels, unavailable, onRetry }: EmptyStateProps) {
  const retry = (
    <Button variant="outline" size="sm" onClick={onRetry}>
      <RotateCw />
      Retry
    </Button>
  )

  return (
    <div className="flex flex-col items-center gap-3 pt-[18vh] text-center">
      <BrainCircuit className="size-12 text-primary" strokeWidth={1.5} />
      <h1 className="text-2xl font-semibold tracking-tight">Many minds, one interface.</h1>
      {error ? (
        <div className="flex flex-col items-center gap-2 text-sm">
          <p className="text-destructive">{error}</p>
          {retry}
        </div>
      ) : ready && !hasModels ? (
        <div className="flex flex-col items-center gap-2 text-sm">
          <p className="text-destructive">No model available. Is Ollama running?</p>
          {retry}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Pick a model and ask anything. Local models run on your own GPU.
        </p>
      )}
      {!error && unavailable.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Unavailable right now: {unavailable.map((p) => p.name).join(", ")}.
          {hasModels && " The other models still work."}
        </p>
      )}
    </div>
  )
}
