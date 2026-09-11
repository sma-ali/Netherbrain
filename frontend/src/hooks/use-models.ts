import { useCallback, useEffect, useState } from "react"

import { fetchModels, type ModelInfo, type ProviderStatus } from "@/lib/api"

interface ModelsState {
  status: "loading" | "ready" | "error"
  models: ModelInfo[]
  providers: ProviderStatus[]
  error: string | null
}

const LOADING: ModelsState = { status: "loading", models: [], providers: [], error: null }

/**
 * Charge les modèles et l'état des fournisseurs depuis l'API,
 * avec possibilité de réessayer si le backend est éteint.
 */
export function useModels() {
  const [state, setState] = useState<ModelsState>(LOADING)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchModels(controller.signal)
      .then(({ models, providers }) => setState({ status: "ready", models, providers, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: "error",
          models: [],
          providers: [],
          error: error instanceof Error ? error.message : String(error),
        })
      })
    // Nettoyage : annule la requête si le composant disparaît ou relance avant la réponse.
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState(LOADING)
    setAttempt((n) => n + 1)
  }, [])

  return { ...state, retry }
}
