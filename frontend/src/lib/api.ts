import { SSEParser, type SSEMessage } from "@/lib/sse"

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type Role = "system" | "user" | "assistant"

export interface ChatMessage {
  role: Role
  content: string
}

export interface ModelInfo {
  id: string
  provider: string
}

export interface ProviderStatus {
  name: string
  available: boolean
  error: string | null
}

export interface ModelsResponse {
  models: ModelInfo[]
  providers: ProviderStatus[]
}

export interface ChatMetrics {
  total_ms: number
  ttft_ms: number | null
  prompt_tokens?: number
  completion_tokens?: number
  tokens_per_second?: number | null
}

export type ChatEvent =
  | { type: "reasoning"; content: string }
  | { type: "token"; content: string }
  | { type: "done"; metrics: ChatMetrics }
  | { type: "error"; message: string }

/** Unique key of a model across providers. Provider names never contain "/". */
export const modelKey = (model: ModelInfo) => `${model.provider}/${model.id}`

export async function fetchModels(signal?: AbortSignal): Promise<ModelsResponse> {
  const response = await request("/api/models", { signal })
  return response.json()
}

/**
 * POST a conversation and yield the answer event by event.
 *
 * The browser's EventSource only supports GET, so the SSE stream is read by hand
 * from the fetch response body.
 */
export async function* streamChat(
  model: ModelInfo,
  messages: ChatMessage[],
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await request("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider: model.provider, model: model.id, messages }),
    signal,
  })
  if (!response.body) throw new Error("The API returned an empty response")

  const parser = new SSEParser()
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) return
      for (const message of parser.feed(value)) {
        const event = toChatEvent(message)
        if (event) yield event
      }
    }
  } finally {
    // Closes the connection if the consumer stops early; no-op once the stream has ended.
    await reader.cancel().catch(() => {})
  }
}

function toChatEvent({ event, data }: SSEMessage): ChatEvent | null {
  const payload = JSON.parse(data)
  switch (event) {
    case "reasoning":
    case "token":
      return { type: event, content: payload.content }
    case "done":
      return { type: "done", metrics: payload }
    case "error":
      return { type: "error", message: payload.message }
    default:
      return null
  }
}

async function request(path: string, init: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, init)
  } catch (error) {
    if (init.signal?.aborted) throw error
    throw new Error(`Cannot reach the Netherbrain API at ${API_URL}`)
  }
  if (!response.ok) throw new Error(await errorMessage(response))
  return response
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body.detail === "string") return body.detail
  } catch {
    // Not JSON: fall back to the status line.
  }
  return `HTTP ${response.status} ${response.statusText}`
}
