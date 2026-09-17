import { useCallback, useRef, useState } from "react"

import type { UIMessage } from "@/hooks/use-chat"
import {
  createComparison,
  getComparison,
  modelKey,
  streamChat,
  streamComparisonResult,
  type ChatEvent,
  type ComparisonDetail,
  type ComparisonResultData,
  type ModelInfo,
} from "@/lib/api"
import { planRuns } from "@/lib/compare"

export type ContenderState = "queued" | "running" | "done" | "error" | "stopped"

/** Un modèle en lice : son état et la réponse qu'il est en train d'écrire. */
export interface Contender {
  key: string
  model: ModelInfo
  state: ContenderState
  message: UIMessage
}

interface UseComparisonOptions {
  /** Enregistrer la comparaison côté serveur ; false quand l'historique est indisponible. */
  persist: boolean
  /** Appelé quand une comparaison a été enregistrée. */
  onSaved: () => void
}

/** La comparaison affichée : la même question posée à plusieurs modèles, et leurs réponses. */
export function useComparison({ persist, onSaved }: UseComparisonOptions) {
  const [comparisonId, setComparisonId] = useState<string | null>(null)
  const [prompt, setPrompt] = useState<string | null>(null)
  const [contenders, setContenders] = useState<Contender[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  // La dernière comparaison ouverte : ignore les réponses arrivées trop tard.
  const requestedRef = useRef<string | null>(null)

  const run = useCallback(
    async (content: string, models: ModelInfo[], localProviders: Set<string>) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      requestedRef.current = null
      setComparisonId(null)
      setPrompt(content)
      setError(null)
      setContenders(
        models.map((model) => ({
          key: modelKey(model),
          model,
          state: "queued",
          message: { id: crypto.randomUUID(), role: "assistant", content: "", model },
        })),
      )
      setRunning(true)

      // Une comparaison remplacée par une autre (ou quittée) ne doit plus rien modifier.
      const isCurrent = () => abortRef.current === controller

      // Le serveur crée la comparaison et une réponse « en attente » par modèle. S'il n'y
      // arrive pas (base en panne), on compare quand même, sans rien enregistrer.
      let saved: ComparisonDetail | null = null
      if (persist) {
        try {
          saved = await createComparison(content, models)
        } catch {
          saved = null
        }
      }
      if (!isCurrent()) return
      const savedId = saved?.id ?? null
      const resultIds = new Map(models.map((model, i) => [modelKey(model), saved?.results[i]?.id]))
      if (savedId) {
        requestedRef.current = savedId
        setComparisonId(savedId)
        onSaved()
      }

      const patch = (key: string, update: (c: Contender) => Partial<Contender>) => {
        if (!isCurrent()) return
        setContenders((prev) => prev.map((c) => (c.key === key ? { ...c, ...update(c) } : c)))
      }
      const patchMessage = (key: string, update: (m: UIMessage) => Partial<UIMessage>) =>
        patch(key, (c) => ({ message: { ...c.message, ...update(c.message) } }))

      const runOne = async (model: ModelInfo) => {
        const key = modelKey(model)
        const resultId = resultIds.get(key)
        patch(key, () => ({ state: "running" }))
        try {
          const events: AsyncGenerator<ChatEvent> =
            savedId && resultId
              ? streamComparisonResult(savedId, resultId, controller.signal)
              : // La même question, sans historique, pour chaque modèle : c'est équitable.
                streamChat(model, [{ role: "user", content }], controller.signal)
          for await (const event of events) {
            switch (event.type) {
              case "reasoning":
                patchMessage(key, (m) => ({ reasoning: (m.reasoning ?? "") + event.content }))
                break
              case "token":
                patchMessage(key, (m) => ({ content: m.content + event.content }))
                break
              case "done":
                patchMessage(key, () => ({ metrics: event.metrics }))
                patch(key, () => ({ state: "done" }))
                break
              case "error":
                patchMessage(key, () => ({ error: event.message }))
                patch(key, () => ({ state: "error" }))
                break
            }
          }
          // Stream terminé sans événement final : on le considère comme fini.
          patch(key, (c) => (c.state === "running" ? { state: "done" } : {}))
        } catch (err) {
          if (controller.signal.aborted) {
            patchMessage(key, () => ({ stopped: true }))
            patch(key, () => ({ state: "stopped" }))
          } else {
            const message = err instanceof Error ? err.message : String(err)
            patchMessage(key, () => ({ error: message }))
            patch(key, () => ({ state: "error" }))
          }
        }
      }

      const { sequential, parallel } = planRuns(models, localProviders)
      const localQueue = (async () => {
        for (const model of sequential) {
          if (controller.signal.aborted) break
          await runOne(model)
        }
      })()
      await Promise.all([localQueue, ...parallel.map((model) => runOne(model))])

      if (!isCurrent()) return
      // Après un arrêt, les modèles restés en file d'attente ne partiront jamais.
      setContenders((prev) =>
        prev.map((c) => (c.state === "queued" ? { ...c, state: "stopped" } : c)),
      )
      abortRef.current = null
      setRunning(false)
    },
    [onSaved, persist],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  const open = useCallback(async (id: string) => {
    abortRef.current?.abort()
    abortRef.current = null
    requestedRef.current = id
    setRunning(false)
    setComparisonId(id)
    setPrompt(null)
    setContenders([])
    setError(null)
    try {
      const comparison = await getComparison(id)
      if (requestedRef.current !== id) return
      setPrompt(comparison.prompt)
      setContenders(comparison.results.map(toContender))
    } catch (err) {
      if (requestedRef.current !== id) return
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    requestedRef.current = null
    setRunning(false)
    setComparisonId(null)
    setPrompt(null)
    setContenders([])
    setError(null)
  }, [])

  return { comparisonId, prompt, contenders, running, error, run, stop, open, reset }
}

function toContender(result: ComparisonResultData): Contender {
  const model = { provider: result.provider, id: result.model }
  return {
    key: modelKey(model),
    model,
    // Une réponse jamais terminée en base (serveur arrêté entre-temps…) compte comme arrêtée.
    state: result.state === "pending" || result.state === "running" ? "stopped" : result.state,
    message: {
      id: result.id,
      role: "assistant",
      content: result.content,
      reasoning: result.reasoning ?? undefined,
      model,
      metrics: result.metrics ?? undefined,
      error: result.error ?? undefined,
      stopped: result.state === "stopped",
    },
  }
}
