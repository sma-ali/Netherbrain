import { useCallback, useState } from "react"

import { EMPTY_MEMORY, type ModelMemory } from "@/lib/models"

const STORAGE_KEY = "netherbrain-models"

/** Les derniers modèles choisis, gardés dans ce navigateur d'une visite à l'autre. */
export function useModelMemory() {
  // Lu au premier rendu : pendant le rendu serveur, il n'y a pas de stockage, d'où le défaut.
  const [memory, setMemory] = useState<ModelMemory>(read)

  const remember = useCallback((next: ModelMemory) => {
    setMemory(next)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // Stockage bloqué (navigation privée…) : le choix vaut pour cette visite.
    }
  }, [])

  return { memory, remember }
}

function read(): ModelMemory {
  if (typeof window === "undefined") return EMPTY_MEMORY
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null")
    return {
      chat: typeof saved?.chat === "string" ? saved.chat : null,
      agent: typeof saved?.agent === "string" ? saved.agent : null,
    }
  } catch {
    return EMPTY_MEMORY
  }
}
