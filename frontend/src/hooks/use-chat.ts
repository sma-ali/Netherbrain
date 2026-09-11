import { useCallback, useRef, useState } from "react"

import {
  createConversation,
  getConversation,
  streamChat,
  streamMessage,
  type ChatEvent,
  type ChatMetrics,
  type ModelInfo,
  type StoredMessage,
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
}

export type ChatStatus = "idle" | "streaming"

interface UseChatOptions {
  /** Enregistrer la conversation côté serveur ; false quand l'historique est indisponible. */
  persist: boolean
  /** Appelé quand une conversation a été créée ou modifiée côté serveur. */
  onSaved: () => void
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
    async (content: string, model: ModelInfo) => {
      const userMessage: UIMessage = { id: crypto.randomUUID(), role: "user", content }
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
            id = (await createConversation()).id
            requestedRef.current = id
            setConversationId(id)
            onSaved()
          }
          events = streamMessage(id, model, content, controller.signal)
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
            case "reasoning":
              patchAnswer((m) => ({ reasoning: (m.reasoning ?? "") + event.content }))
              break
            case "token":
              patchAnswer((m) => ({ content: m.content + event.content }))
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
          patchAnswer(() => ({ error: error instanceof Error ? error.message : String(error) }))
        }
      } finally {
        abortRef.current = null
        setStatus("idle")
        if (persist) onSaved()
      }
    },
    [conversationId, messages, onSaved, persist],
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

  return { conversationId, messages, status, send, stop, open, reset }
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
  }
}
