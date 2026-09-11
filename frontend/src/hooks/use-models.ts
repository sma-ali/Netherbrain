import { useCallback, useEffect, useState } from "react"

import { fetchModels, type ModelInfo, type ProviderStatus } from "@/lib/api"

interface ModelsState {
  status: "loading" | "ready" | "error"
  models: ModelInfo[]
  providers: ProviderStatus[]
  error: string | null
}

const LOADING: ModelsState = { status: "loading", models: [], providers: [], error: null }

/** Loads models and provider statuses from the API, with a retry for when the backend is down. */
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
    // Cleanup: cancel the request if the component unmounts or retries first.
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState(LOADING)
    setAttempt((n) => n + 1)
  }, [])

  return { ...state, retry }
}
