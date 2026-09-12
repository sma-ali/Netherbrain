"use client"

import { BookOpen, BrainCircuit, ChevronRight, TriangleAlert } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Metrics } from "@/components/metrics"
import { ToolStep } from "@/components/tool-step"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import type { UIMessage } from "@/hooks/use-chat"
import type { Source, ToolDecision } from "@/lib/api"

interface MessageProps {
  message: UIMessage
  streaming: boolean
  /** Afficher le modèle au-dessus de la réponse (inutile quand une colonne le montre déjà). */
  showModel?: boolean
  /** Réponse à une demande d'autorisation de l'agent. */
  onApprove?: (callId: string, decision: ToolDecision) => void
}

export function Message({ message, streaming, showModel = true, onApprove }: MessageProps) {
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

      {message.steps && message.steps.length > 0 && (
        <div className="flex flex-col gap-2">
          {message.steps.map((step) => (
            <ToolStep key={step.id} step={step} onApprove={onApprove} />
          ))}
        </div>
      )}

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
      {message.sourcesWarning && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <TriangleAlert className="size-3.5 shrink-0" />
          {message.sourcesWarning}
        </p>
      )}
      {message.sources && message.sources.length > 0 && <Sources sources={message.sources} />}
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

/** Les extraits de documents sur lesquels s'appuie la réponse, numérotés comme les [1] cités. */
function Sources({ sources }: { sources: Source[] }) {
  return (
    <Collapsible>
      <CollapsibleTrigger className="group flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ChevronRight className="size-4 transition-transform group-data-panel-open:rotate-90" />
        <BookOpen className="size-4" />
        {sources.length} {sources.length === 1 ? "source" : "sources"}
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mt-2 flex flex-col gap-3 border-l-2 border-primary/40 pl-3">
          {sources.map((source, index) => (
            <li key={`${source.document_id}-${index}`} className="text-sm">
              <p className="font-medium">
                [{index + 1}] {source.document_name}
                {source.page != null && `, page ${source.page}`}
                <span className="ml-2 font-mono text-xs text-muted-foreground">
                  {Math.round(source.score * 100)}% match
                </span>
              </p>
              <p className="line-clamp-3 text-muted-foreground" title={source.content}>
                {source.content}
              </p>
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  )
}
