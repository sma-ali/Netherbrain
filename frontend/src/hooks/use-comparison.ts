import { useCallback, useRef, useState } from "react"

import type { UIMessage } from "@/hooks/use-chat"
import { modelKey, streamChat, type ModelInfo } from "@/lib/api"
import { planRuns } from "@/lib/compare"

export type ContenderState = "queued" | "running" | "done" | "error" | "stopped"

/** Un modèle en lice : son état et la réponse qu'il est en train d'écrire. */
export interface Contender {
  key: string
  model: ModelInfo
  state: ContenderState
  message: UIMessage
}

/** Pose la même question à plusieurs modèles et suit toutes leurs réponses. */
export function useComparison() {
  const [prompt, setPrompt] = useState<string | null>(null)
  const [contenders, setContenders] = useState<Contender[]>([])
  const [running, setRunning] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const run = useCallback(
    async (content: string, models: ModelInfo[], localProviders: Set<string>) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setPrompt(content)
      setContenders(
        models.map((model) => ({
          key: modelKey(model),
          model,
          state: "queued",
          message: { id: crypto.randomUUID(), role: "assistant", content: "", model },
        })),
      )
      setRunning(true)

      // Une comparaison remplacée par une nouvelle ne doit plus rien modifier à l'écran.
      const patch = (key: string, update: (c: Contender) => Partial<Contender>) => {
        if (abortRef.current !== controller) return
        setContenders((prev) => prev.map((c) => (c.key === key ? { ...c, ...update(c) } : c)))
      }
      const patchMessage = (key: string, update: (m: UIMessage) => Partial<UIMessage>) =>
        patch(key, (c) => ({ message: { ...c.message, ...update(c.message) } }))

      const runOne = async (model: ModelInfo) => {
        const key = modelKey(model)
        patch(key, () => ({ state: "running" }))
        try {
          // La même question, sans historique, pour chaque modèle : la comparaison reste équitable.
          const question = [{ role: "user" as const, content }]
          for await (const event of streamChat(model, question, controller.signal)) {
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
        } catch (error) {
          if (controller.signal.aborted) {
            patchMessage(key, () => ({ stopped: true }))
            patch(key, () => ({ state: "stopped" }))
          } else {
            const message = error instanceof Error ? error.message : String(error)
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
      await Promise.all([localQueue, ...parallel.map(runOne)])

      if (abortRef.current !== controller) return
      // Après un arrêt, les modèles restés en file d'attente ne partiront jamais.
      setContenders((prev) =>
        prev.map((c) => (c.state === "queued" ? { ...c, state: "stopped" } : c)),
      )
      abortRef.current = null
      setRunning(false)
    },
    [],
  )

  const stop = useCallback(() => abortRef.current?.abort(), [])

  return { prompt, contenders, running, run, stop }
}
