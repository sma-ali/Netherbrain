import type { ModelCard } from "@/lib/api"

export type CatalogFilter = "local" | "remote" | "free" | "reasoning" | "vision" | "tools" | "code"
export type CatalogSort = "name" | "speed" | "usage" | "context" | "size"

export const FILTERS: { value: CatalogFilter; label: string; hint: string }[] = [
  { value: "local", label: "Local", hint: "Runs on your GPU and works offline" },
  { value: "remote", label: "Cloud", hint: "Runs on the provider's servers" },
  { value: "free", label: "Free", hint: "No cost per request" },
  { value: "reasoning", label: "Reasoning", hint: "Thinks step by step before answering" },
  { value: "vision", label: "Vision", hint: "Understands images" },
  { value: "tools", label: "Tools", hint: "Can call functions, for agents" },
  { value: "code", label: "Code", hint: "Specialised in programming" },
]

export const SORTS: { value: CatalogSort; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "speed", label: "Measured speed" },
  { value: "usage", label: "Most used" },
  { value: "context", label: "Context length" },
  { value: "size", label: "Model size" },
]

export const CAPABILITY_LABELS: Record<string, string> = {
  reasoning: "Reasoning",
  tools: "Tools",
  vision: "Vision",
  code: "Code",
  embedding: "Embeddings",
}

function matches(card: ModelCard, filter: CatalogFilter): boolean {
  switch (filter) {
    case "local":
      return card.local
    case "remote":
      return !card.local
    case "free":
      return card.free === true
    default:
      return card.capabilities.includes(filter)
  }
}

/** Garde les modèles qui contiennent le texte cherché ET remplissent tous les filtres cochés. */
export function filterModels(
  cards: ModelCard[],
  query: string,
  filters: Set<CatalogFilter>,
): ModelCard[] {
  const needle = query.trim().toLowerCase()
  return cards.filter(
    (card) =>
      (needle === "" ||
        [card.id, card.name, card.provider, card.description ?? ""].some((text) =>
          text.toLowerCase().includes(needle),
        )) &&
      [...filters].every((filter) => matches(card, filter)),
  )
}

/** La valeur qui sert au tri ; null quand elle est inconnue (modèle jamais essayé…). */
function sortValue(card: ModelCard, sort: CatalogSort): number | null {
  switch (sort) {
    case "speed":
      return card.stats?.avg_tokens_per_second ?? null
    case "usage":
      return card.stats?.answers ?? null
    case "context":
      return card.context_length
    case "size":
      return card.parameters_b
    default:
      return null
  }
}

/** Trie du plus grand au plus petit ; les modèles sans valeur passent à la fin, par nom. */
export function sortModels(cards: ModelCard[], sort: CatalogSort): ModelCard[] {
  return [...cards].sort((a, b) => {
    const valueA = sortValue(a, sort)
    const valueB = sortValue(b, sort)
    if (valueA === null || valueB === null) {
      if (valueA !== valueB) return valueA === null ? 1 : -1
      return a.name.localeCompare(b.name)
    }
    return valueB - valueA
  })
}
