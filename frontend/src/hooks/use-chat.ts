import { useCallback, useRef, useState } from "react"

import { streamChat, type ChatMetrics, type ModelInfo } from "@/lib/api"

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

/** Conversation state: the message list, and sending/stopping a streamed answer. */
export function useChat() {
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [status, setStatus] = useState<ChatStatus>("idle")
  const abortRef = useRef<AbortController | null>(null)

  const send = useCallback(
    async (content: string, model: ModelInfo) => {
      const userMessage: UIMessage = { id: crypto.randomUUID(), role: "user", content }
      const assistantId = crypto.randomUUID()

      // LLM APIs are stateless: the whole conversation is sent with every request.
      const history = [...messages, userMessage]
        .filter((message) => message.content)
        .map(({ role, content }) => ({ role, content }))

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
        for await (const event of streamChat(model, history, controller.signal)) {
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
      }
    },
    [messages],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    setMessages([])
  }, [])

  return { messages, status, send, stop, reset }
}
