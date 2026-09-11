"use client"

import { BrainCircuit, RotateCw, SquarePen } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Composer } from "@/components/composer"
import { Message } from "@/components/message"
import { ModelPicker } from "@/components/model-picker"
import { Button } from "@/components/ui/button"
import { useChat } from "@/hooks/use-chat"
import { useModels } from "@/hooks/use-models"

export function Chat() {
  const { messages, status, send, stop, reset } = useChat()
  const models = useModels()
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  // Derived state: fall back to the first model until the user picks one.
  const model = selectedModel ?? models.models[0]?.id ?? null

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  // Follow the answer as it streams, unless the user scrolled up to read.
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
            value={model}
            onChange={setSelectedModel}
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
            <EmptyState error={models.status === "error" ? models.error : null} onRetry={models.retry} />
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

function EmptyState({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 pt-[18vh] text-center">
      <BrainCircuit className="size-12 text-primary" strokeWidth={1.5} />
      <h1 className="text-2xl font-semibold tracking-tight">Many minds, one interface.</h1>
      {error ? (
        <div className="flex flex-col items-center gap-2 text-sm">
          <p className="text-destructive">{error}</p>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCw />
            Retry
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Pick a model and ask anything. Local models run on your own GPU.
        </p>
      )}
    </div>
  )
}
