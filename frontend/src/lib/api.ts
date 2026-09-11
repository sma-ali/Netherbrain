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
  // Modèles exécutés sur la machine de l'utilisateur : ils se partagent le GPU.
  local: boolean
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

/** Un extrait de document retrouvé pour répondre (RAG). */
export interface Source {
  document_id: string
  document_name: string
  page: number | null
  content: string
  // Similarité cosinus avec la question : proche de 1 = même sens.
  score: number
}

export type ChatEvent =
  | { type: "sources"; sources: Source[]; warning: string | null }
  | { type: "reasoning"; content: string }
  | { type: "token"; content: string }
  | { type: "done"; metrics: ChatMetrics }
  | { type: "error"; message: string }

// --- Catalogue des modèles ---

export interface ModelStats {
  answers: number
  avg_ttft_ms: number | null
  avg_tokens_per_second: number | null
}

export interface ModelCard {
  id: string
  provider: string
  local: boolean
  name: string
  description: string | null
  family: string | null
  parameters_b: number | null
  quantization: string | null
  size_bytes: number | null
  context_length: number | null
  // Parmi : reasoning, tools, vision, code, embedding.
  capabilities: string[]
  free: boolean | null
  stats: ModelStats | null
}

export interface CatalogResponse {
  models: ModelCard[]
  providers: ProviderStatus[]
  stats_available: boolean
}

// --- Conversations enregistrées ---

export interface ConversationSummary {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface StoredMessage {
  id: string
  role: "user" | "assistant"
  content: string
  reasoning: string | null
  provider: string | null
  model: string | null
  metrics: ChatMetrics | null
  error: string | null
  stopped: boolean
  sources: Source[] | null
  created_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: StoredMessage[]
}

// --- Comparaisons enregistrées ---

export type ResultState = "pending" | "running" | "done" | "error" | "stopped"

export interface ComparisonResultData {
  id: string
  position: number
  provider: string
  model: string
  state: ResultState
  content: string
  reasoning: string | null
  metrics: ChatMetrics | null
  error: string | null
}

export interface ComparisonSummary {
  id: string
  prompt: string
  created_at: string
  models: string[]
}

export interface ComparisonDetail {
  id: string
  prompt: string
  created_at: string
  results: ComparisonResultData[]
}

// --- Documents (RAG) ---

export interface DocumentInfo {
  id: string
  name: string
  content_type: string
  size_bytes: number
  // processing : indexation en cours ; ready : utilisable ; error : voir `error`.
  status: "processing" | "ready" | "error"
  error: string | null
  chunk_count: number
  created_at: string
}

/** Clé unique d'un modèle, tous fournisseurs confondus. Un nom de fournisseur ne contient jamais "/". */
export const modelKey = (model: ModelInfo) => `${model.provider}/${model.id}`

export async function fetchModels(signal?: AbortSignal): Promise<ModelsResponse> {
  const response = await request("/api/models", { signal })
  return response.json()
}

export async function fetchCatalog(signal?: AbortSignal): Promise<CatalogResponse> {
  const response = await request("/api/catalog", { signal })
  return response.json()
}

// --- Conversations ---

export async function listConversations(signal?: AbortSignal): Promise<ConversationSummary[]> {
  const response = await request("/api/conversations", { signal })
  return response.json()
}

export async function createConversation(): Promise<ConversationSummary> {
  const response = await request("/api/conversations", { method: "POST" })
  return response.json()
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const response = await request(`/api/conversations/${id}`, {})
  return response.json()
}

export async function deleteConversation(id: string): Promise<void> {
  await request(`/api/conversations/${id}`, { method: "DELETE" })
}

/**
 * Envoie un message dans une conversation enregistrée : le serveur connaît déjà l'historique.
 * `useDocuments` : le serveur cherche dans les documents importés et s'en sert (RAG).
 */
export async function* streamMessage(
  conversationId: string,
  model: ModelInfo,
  content: string,
  signal: AbortSignal,
  useDocuments = false,
): AsyncGenerator<ChatEvent> {
  const response = await request(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: model.provider,
      model: model.id,
      content,
      use_documents: useDocuments,
    }),
    signal,
  })
  yield* readEvents(response)
}

// --- Comparaisons ---

export async function listComparisons(signal?: AbortSignal): Promise<ComparisonSummary[]> {
  const response = await request("/api/comparisons", { signal })
  return response.json()
}

export async function createComparison(
  prompt: string,
  models: ModelInfo[],
): Promise<ComparisonDetail> {
  const response = await request("/api/comparisons", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt,
      contenders: models.map((model) => ({ provider: model.provider, model: model.id })),
    }),
  })
  return response.json()
}

export async function getComparison(id: string): Promise<ComparisonDetail> {
  const response = await request(`/api/comparisons/${id}`, {})
  return response.json()
}

export async function deleteComparison(id: string): Promise<void> {
  await request(`/api/comparisons/${id}`, { method: "DELETE" })
}

/** Lance la réponse d'un modèle d'une comparaison enregistrée ; le serveur l'enregistre. */
export async function* streamComparisonResult(
  comparisonId: string,
  resultId: string,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const response = await request(`/api/comparisons/${comparisonId}/results/${resultId}/run`, {
    method: "POST",
    signal,
  })
  yield* readEvents(response)
}

// --- Documents ---

export async function listDocuments(signal?: AbortSignal): Promise<DocumentInfo[]> {
  const response = await request("/api/documents", { signal })
  return response.json()
}

/** Envoie un fichier ; le serveur répond tout de suite et l'indexe en tâche de fond. */
export async function uploadDocument(file: File): Promise<DocumentInfo> {
  const body = new FormData()
  body.append("file", file)
  // Pas d'en-tête Content-Type : le navigateur l'écrit lui-même, avec la « boundary »
  // qui sépare les parties du formulaire.
  const response = await request("/api/documents", { method: "POST", body })
  return response.json()
}

export async function deleteDocument(id: string): Promise<void> {
  await request(`/api/documents/${id}`, { method: "DELETE" })
}

// --- Mode sans historique ---

/** Envoie toute la conversation ; rien n'est enregistré côté serveur. */
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
  yield* readEvents(response)
}

/**
 * Lit la réponse SSE et renvoie les événements un par un.
 *
 * L'EventSource du navigateur ne gère que GET : le stream SSE est donc lu à la main
 * depuis le corps de la réponse de fetch.
 */
async function* readEvents(response: Response): AsyncGenerator<ChatEvent> {
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
    // Ferme la connexion si l'appelant s'arrête avant la fin ; sans effet si le stream est fini.
    await reader.cancel().catch(() => {})
  }
}

function toChatEvent({ event, data }: SSEMessage): ChatEvent | null {
  const payload = JSON.parse(data)
  switch (event) {
    case "sources":
      return { type: "sources", sources: payload.sources, warning: payload.warning ?? null }
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
    // Pas du JSON : on se rabat sur la ligne de statut.
  }
  return `HTTP ${response.status} ${response.statusText}`
}
