"use client"

import { BrainCircuit, ChevronRight, TriangleAlert } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Metrics } from "@/components/metrics"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import type { UIMessage } from "@/hooks/use-chat"

interface MessageProps {
  message: UIMessage
  streaming: boolean
  /** Afficher le modèle au-dessus de la réponse (inutile quand une colonne le montre déjà). */
  showModel?: boolean
}

export function Message({ message, streaming, showModel = true }: MessageProps) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl bg-secondary px-4 py-2.5 whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    )
  }

  const thinking = streaming && !message.content

  return (
    <div className="flex flex-col gap-2">
      {showModel && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <BrainCircuit className="size-4 text-primary" />
          {message.model && (
            <>
              <span className="font-mono">{message.model.id}</span>
              <span className="text-muted-foreground/70">via {message.model.provider}</span>
            </>
          )}
        </div>
      )}

      {message.reasoning && <Reasoning text={message.reasoning} active={thinking} />}

      {message.content ? (
        // react-markdown n'affiche jamais de HTML brut venant du modèle : pas de XSS possible.
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      ) : (
        thinking && !message.reasoning && <p className="animate-pulse text-muted-foreground">…</p>
      )}

      {message.error && (
        <p className="flex items-center gap-2 text-sm text-destructive">
          <TriangleAlert className="size-4 shrink-0" />
          {message.error}
        </p>
      )}
      {message.stopped && <p className="text-xs text-muted-foreground">Stopped.</p>}
      {message.metrics && <Metrics metrics={message.metrics} />}
    </div>
  )
}

function Reasoning({ text, active }: { text: string; active: boolean }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-4 transition-transform group-data-panel-open:rotate-90" />
        <span className={active ? "animate-pulse" : undefined}>
          {active ? "Thinking…" : "Reasoning"}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <p className="mt-2 max-h-80 overflow-y-auto border-l-2 border-primary/40 pl-3 text-sm whitespace-pre-wrap text-muted-foreground">
          {text}
        </p>
      </CollapsibleContent>
    </Collapsible>
  )
}
