import { useCallback, useEffect, useState } from "react"

import { fetchCatalog, type ModelCard, type ProviderStatus } from "@/lib/api"

interface CatalogState {
  status: "loading" | "ready" | "error"
  models: ModelCard[]
  providers: ProviderStatus[]
  // false : la base est indisponible, les fiches arrivent sans les mesures.
  statsAvailable: boolean
  error: string | null
}

const LOADING: CatalogState = {
  status: "loading",
  models: [],
  providers: [],
  statsAvailable: true,
  error: null,
}

/** Le catalogue des modèles, avec possibilité de le recharger. */
export function useCatalog() {
  const [state, setState] = useState<CatalogState>(LOADING)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetchCatalog(controller.signal)
      .then(({ models, providers, stats_available }) =>
        setState({ status: "ready", models, providers, statsAvailable: stats_available, error: null }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setState({
          ...LOADING,
          status: "error",
          error: error instanceof Error ? error.message : String(error),
        })
      })
    return () => controller.abort()
  }, [attempt])

  const retry = useCallback(() => {
    setState(LOADING)
    setAttempt((n) => n + 1)
  }, [])

  return { ...state, retry }
}
