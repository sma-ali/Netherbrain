import { useCallback, useEffect, useState } from "react"

interface SavedListState<T> {
  // "error" : l'historique est indisponible (base de données en panne, par exemple).
  status: "loading" | "ready" | "error"
  items: T[]
}

/**
 * Une liste d'éléments enregistrés côté serveur : conversations ou comparaisons.
 * `load` et `remove` doivent être des fonctions stables (définies hors du composant).
 */
export function useSavedList<T extends { id: string }>(
  load: (signal: AbortSignal) => Promise<T[]>,
  remove: (id: string) => Promise<void>,
) {
  const [state, setState] = useState<SavedListState<T>>({ status: "loading", items: [] })
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
      .then((items) => setState({ status: "ready", items }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error", items: [] })
      })
    // Nettoyage : annule la requête si le composant disparaît ou recharge avant la réponse.
    return () => controller.abort()
  }, [load, version])

  // Recharge la liste ; l'ancienne reste affichée pendant ce temps (pas de clignotement).
  const refresh = useCallback(() => setVersion((n) => n + 1), [])

  const removeItem = useCallback(
    async (id: string) => {
      await remove(id)
      setState((prev) => ({ ...prev, items: prev.items.filter((item) => item.id !== id) }))
    },
    [remove],
  )

  return { ...state, refresh, remove: removeItem }
}
