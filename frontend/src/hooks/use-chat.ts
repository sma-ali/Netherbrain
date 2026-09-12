import { useCallback, useRef, useState } from "react"

import {
  approveTool,
  createConversation,
  getConversation,
  streamChat,
  streamMessage,
  type AgentStep,
  type ChatEvent,
  type ChatMetrics,
  type ModelInfo,
  type Source,
  type StoredMessage,
  type ToolDecision,
} from "@/lib/api"

export interface UIMessage {
  id: string
  role: "user" | "assistant"
  content: string
  reasoning?: string
  model?: ModelInfo
  metrics?: ChatMetrics
  error?: string
  stopped?: boolean
  // Extraits de documents utilisés pour répondre (RAG), et avertissement éventuel.
  sources?: Source[]
  sourcesWarning?: string
  // Les outils utilisés par l'agent, dans l'ordre où il les a demandés.
  steps?: AgentStep[]
}

export type ChatStatus = "idle" | "streaming"

interface UseChatOptions {
  /** Enregistrer la conversation côté serveur ; false quand l'historique est indisponible. */
  persist: boolean
  /** Appelé quand une conversation a été créée ou modifiée côté serveur. */
  onSaved: () => void
}

interface SendOptions {
  /** S'appuyer sur les documents importés (RAG) ; uniquement avec l'historique. */
  useDocuments?: boolean
  /** Le projet d'une nouvelle conversation ; ignoré si la conversation existe déjà. */
  projectId?: string | null
  /** Mode agent : le modèle peut lire et modifier les fichiers du projet. */
  agent?: boolean
}

/** Remplace un appel d'outil dans la liste, sans toucher aux autres. */
function updateStep(
  steps: AgentStep[] | undefined,
  id: string,
  changes: Partial<AgentStep>,
): AgentStep[] {
  return (steps ?? []).map((step) => (step.id === id ? { ...step, ...changes } : step))
}

/** La conversation affichée : ses messages, l'envoi et l'arrêt d'une réponse streamée. */
export function useChat({ persist, onSaved }: UseChatOptions) {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [status, setStatus] = useState<ChatStatus>("idle")
  const abortRef = useRef<AbortController | null>(null)
  // La dernière conversation demandée : ignore les réponses arrivées trop tard
  // si l'utilisateur a cliqué entre-temps sur une autre (« race condition »).
  const requestedRef = useRef<string | null>(null)

  const send = useCallback(
    async (
      content: string,
      model: ModelInfo,
      { useDocuments = false, projectId = null, agent = false }: SendOptions = {},
    ) => {
      const userMessage: UIMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
      }
      const assistantId = crypto.randomUUID()

      setMessages((prev) => [
        ...prev,
        userMessage,
        { id: assistantId, role: "assistant", content: "", model },
      ])

      const patchAnswer = (update: (message: UIMessage) => Partial<UIMessage>) =>
        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId ? { ...message, ...update(message) } : message,
          ),
        )

      const controller = new AbortController()
      abortRef.current = controller
      setStatus("streaming")

      try {
        let events: AsyncGenerator<ChatEvent>
        if (persist) {
          // Le serveur garde l'historique : on n'envoie que le nouveau message.
          let id = conversationId
          if (id === null) {
            id = (await createConversation(projectId)).id
            requestedRef.current = id
            setConversationId(id)
            onSaved()
          }
          events = streamMessage(id, model, content, controller.signal, {
            useDocuments,
            agent,
          })
        } else {
          // Sans historique côté serveur, toute la conversation part à chaque requête
          // (les API de LLM sont sans état).
          const history = [...messages, userMessage]
            .filter((message) => message.content)
            .map(({ role, content }) => ({ role, content }))
          events = streamChat(model, history, controller.signal)
        }

        for await (const event of events) {
          switch (event.type) {
            case "sources":
              patchAnswer(() => ({
                sources: event.sources,
                sourcesWarning: event.warning ?? undefined,
              }))
              break
            case "reasoning":
              patchAnswer((m) => ({
                reasoning: (m.reasoning ?? "") + event.content,
              }))
              break
            case "token":
              patchAnswer((m) => ({ content: m.content + event.content }))
              break
            case "tool_call":
              patchAnswer((m) => ({
                steps: [
                  ...(m.steps ?? []),
                  {
                    id: event.id,
                    name: event.name,
                    summary: event.summary,
                    status: "running",
                    output: "",
                  },
                ],
              }))
              break
            case "tool_request":
              // L'agent attend : le stream ne reprendra qu'après la réponse de l'utilisateur.
              patchAnswer((m) => ({
                steps: updateStep(m.steps, event.id, {
                  status: "asking",
                  arguments: event.arguments,
                }),
              }))
              break
            case "tool_result":
              patchAnswer((m) => ({
                steps: updateStep(m.steps, event.id, {
                  status: event.status as AgentStep["status"],
                  output: event.output,
                }),
              }))
              break
            case "done":
              patchAnswer(() => ({ metrics: event.metrics }))
              break
            case "error":
              patchAnswer(() => ({ error: event.message }))
              break
          }
        }
      } catch (error) {
        if (controller.signal.aborted) {
          patchAnswer(() => ({ stopped: true }))
        } else {
          patchAnswer(() => ({
            error: error instanceof Error ? error.message : String(error),
          }))
        }
      } finally {
        abortRef.current = null
        setStatus("idle")
        if (persist) onSaved()
      }
    },
    [conversationId, messages, onSaved, persist],
  )

  /** Répond à une demande d'autorisation de l'agent (autoriser une fois, toujours, refuser). */
  const approve = useCallback(
    async (callId: string, decision: ToolDecision) => {
      const id = conversationId
      if (id === null) return

      const patchStep = (changes: Partial<AgentStep>) =>
        setMessages((prev) =>
          prev.map((message) =>
            message.steps
              ? {
                  ...message,
                  steps: updateStep(message.steps, callId, changes),
                }
              : message,
          ),
        )

      // La demande disparaît dès le clic ; le résultat arrivera par le stream.
      patchStep({ status: "running" })
      try {
        await approveTool(id, callId, decision)
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        patchStep({ status: "error", output: message })
      }
    },
    [conversationId],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const open = useCallback(async (id: string) => {
    abortRef.current?.abort()
    requestedRef.current = id
    setConversationId(id)
    setMessages([])
    try {
      const conversation = await getConversation(id)
      if (requestedRef.current === id) setMessages(conversation.messages.map(toUIMessage))
    } catch (error) {
      if (requestedRef.current !== id) return
      const message = error instanceof Error ? error.message : String(error)
      setMessages([{ id: "load-error", role: "assistant", content: "", error: message }])
    }
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    requestedRef.current = null
    setConversationId(null)
    setMessages([])
  }, [])

  return { conversationId, messages, status, send, stop, open, reset, approve }
}

function toUIMessage(message: StoredMessage): UIMessage {
  return {
    id: message.id,
    role: message.role,
    content: message.content,
    reasoning: message.reasoning ?? undefined,
    model:
      message.provider && message.model
        ? { provider: message.provider, id: message.model }
        : undefined,
    metrics: message.metrics ?? undefined,
    error: message.error ?? undefined,
    stopped: message.stopped,
    sources: message.sources ?? undefined,
    steps: message.steps ?? undefined,
  }
}
