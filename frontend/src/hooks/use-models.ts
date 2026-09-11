import { useCallback, useEffect, useState } from "react"

import { fetchModels, type ModelInfo } from "@/lib/api"

type ModelsState =
  | { status: "loading"; models: ModelInfo[] }
  | { status: "ready"; models: ModelInfo[] }
  | { status: "error"; models: ModelInfo[]; error: string }

/** Loads the models exposed by the API, with a retry for when the backend is down. */
export function useModels() {
  const [state, setState] = useState<ModelsState>({ status: "loading", models: [] })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchModels(controller.signal)
      .then((models) => setState({ status: "ready", models }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          status: "error",
          models: [],
          error: error instanceof Error ? error.message : String(error),
        })
      })
    // Cleanup: cancel the request if the component unmounts or retries first.
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState({ status: "loading", models: [] })
    setAttempt((n) => n + 1)
  }, [])

  return { ...state, retry }
}
