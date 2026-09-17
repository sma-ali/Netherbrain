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
  type ConversationDetail,
  type ModelInfo,
  type Source,
  type StoredMessage,
  type ToolDecision,
} from "@/lib/api"
import { fromAttachmentInfo, type AttachmentItem } from "@/lib/attachments"

export interface UIMessage {
  id: string
  role: "user" | "assistant"
  content: string
  reasoning?: string
  model?: ModelInfo
  metrics?: ChatMetrics
  error?: string
  stopped?: boolean
  // Passages de fichiers retrouvés pour répondre (RAG), et avertissement éventuel.
  sources?: Source[]
  sourcesWarning?: string
  // Les outils utilisés par l'agent, dans l'ordre où il les a demandés.
  steps?: AgentStep[]
  // Les fichiers joints au message (messages de l'utilisateur).
  attachments?: AttachmentItem[]
}

export type ChatStatus = "idle" | "streaming"

interface UseChatOptions {
  /** Enregistrer la conversation côté serveur ; false quand l'historique est indisponible. */
  persist: boolean
  /** Appelé quand une conversation a été créée ou modifiée côté serveur. */
  onSaved: () => void
}

interface SendOptions {
  /** Le projet d'une nouvelle conversation ; ignoré si la conversation existe déjà. */
  projectId?: string | null
  /** Mode agent : le modèle peut lire et modifier les fichiers du projet. */
  agent?: boolean
  /** Les fichiers joints au message, déjà envoyés et lus par le serveur. */
  attachments?: AttachmentItem[]
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
  // La conversation affichée, lisible sans attendre un nouveau rendu : joindre un fichier
  // puis envoyer aussitôt doit viser la même conversation.
  const conversationRef = useRef<string | null>(null)
  // La création en cours, partagée : plusieurs fichiers joints d'un coup n'en créent qu'une.
  const creatingRef = useRef<Promise<string> | null>(null)

  const select = useCallback((id: string | null) => {
    conversationRef.current = id
    requestedRef.current = id
    setConversationId(id)
  }, [])

  /** La conversation affichée, créée si besoin : au premier message ou au premier fichier. */
  const ensureConversation = useCallback(
    (projectId: string | null = null): Promise<string> => {
      if (conversationRef.current !== null) return Promise.resolve(conversationRef.current)
      creatingRef.current ??= createConversation(projectId)
        .then((conversation) => {
          select(conversation.id)
          return conversation.id
        })
        .finally(() => {
          creatingRef.current = null
        })
      return creatingRef.current
    },
    [select],
  )

  const send = useCallback(
    async (
      content: string,
      model: ModelInfo,
      { projectId = null, agent = false, attachments = [] }: SendOptions = {},
    ) => {
      const userMessage: UIMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        attachments,
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
          const id = await ensureConversation(projectId)
          events = streamMessage(id, model, content, controller.signal, {
            agent,
            attachmentIds: attachments.map((attachment) => attachment.id),
          })
        } else {
          // Sans historique côté serveur, toute la conversation part à chaque requête
          // (les API de LLM sont sans état).
          const history = [...messages, userMessage]
            .filter((message) => message.content)
            .map(({ role, content }) => ({ role, content }))
          events = streamChat(model, history, controller.signal)
        }

        let announced = false
        for await (const event of events) {
          // Le premier événement prouve que le message est enregistré : la conversation
          // peut apparaître dans la barre latérale.
          if (persist && !announced) {
            announced = true
            onSaved()
          }
          switch (event.type) {
            case "sources":
              patchAnswer(() => ({
                sources: event.sources,
                sourcesWarning: event.warning ?? undefined,
              }))
              break
            case "reasoning":
              patchAnswer((m) => ({ reasoning: (m.reasoning ?? "") + event.content }))
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
                  kind: event.kind,
                  arguments: event.arguments,
                  question: event.question,
                  options: event.options,
                  diff: event.diff,
                }),
              }))
              break
            case "tool_result":
              patchAnswer((m) => ({
                steps: updateStep(m.steps, event.id, {
                  status: event.status as AgentStep["status"],
                  output: event.output,
                  // Un appel autorisé d'avance n'a pas eu de demande : le diff arrive ici.
                  ...(event.diff ? { diff: event.diff } : {}),
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
          patchAnswer(() => ({ error: error instanceof Error ? error.message : String(error) }))
        }
      } finally {
        abortRef.current = null
        setStatus("idle")
        if (persist) onSaved()
      }
    },
    [ensureConversation, messages, onSaved, persist],
  )

  /** Répond à l'agent : autoriser une fois ou toujours, refuser, ou répondre à sa question. */
  const approve = useCallback(async (callId: string, decision: ToolDecision, answer?: string) => {
    const id = conversationRef.current
    if (id === null) return

    const patchStep = (changes: Partial<AgentStep>) =>
      setMessages((prev) =>
        prev.map((message) =>
          message.steps
            ? { ...message, steps: updateStep(message.steps, callId, changes) }
            : message,
        ),
      )

    // La demande disparaît dès le clic ; le résultat arrivera par le stream.
    patchStep({ status: "running" })
    try {
      await approveTool(id, callId, decision, answer)
    } catch (error) {
      patchStep({ status: "error", output: error instanceof Error ? error.message : String(error) })
    }
  }, [])

  const stop = useCallback(() => abortRef.current?.abort(), [])

  /** Ouvre une conversation ; rend son contenu, ou null si elle est introuvable ou dépassée. */
  const open = useCallback(
    async (id: string): Promise<ConversationDetail | null> => {
      abortRef.current?.abort()
      select(id)
      setMessages([])
      try {
        const conversation = await getConversation(id)
        if (requestedRef.current !== id) return null
        setMessages(conversation.messages.map(toUIMessage))
        return conversation
      } catch (error) {
        if (requestedRef.current !== id) return null
        const message = error instanceof Error ? error.message : String(error)
        setMessages([{ id: "load-error", role: "assistant", content: "", error: message }])
        return null
      }
    },
    [select],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    select(null)
    setMessages([])
  }, [select])

  return {
    conversationId,
    messages,
    status,
    send,
    stop,
    open,
    reset,
    approve,
    ensureConversation,
  }
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
    attachments: (message.attachments ?? []).map(fromAttachmentInfo),
  }
}
