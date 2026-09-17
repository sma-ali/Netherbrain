/** Mise en forme des conseils : étiquettes, liens vers le chat et la comparaison. */

import type { ModelPick, Needs } from "@/lib/api"

export const ROLE_LABELS: Record<ModelPick["role"], string> = {
  best: "Best match",
  fastest: "Faster option",
  download: "Worth downloading",
  cloud: "Cloud alternative",
}

const TASK_LABELS: Record<string, string> = {
  code: "Code",
  reasoning: "Reasoning",
  writing: "Writing",
  summary: "Long documents",
  chat: "Conversation",
  vision: "Images",
  agent: "Agent",
  multilingual: "Other languages",
}

const REQUIREMENT_LABELS: Record<string, string> = {
  vision: "Reads images",
  tools: "Uses tools",
  long_context: "Long context",
}

export const EXAMPLES = [
  "A Discord bot that summarizes French PDFs",
  "Refactor and debug my React app",
  "Solve maths problems step by step, offline",
  "Describe screenshots of my interface",
]

/** Les besoins compris, en courtes étiquettes : « Code », « Uses tools », « Local only »… */
export function describeNeeds(needs: Needs): string[] {
  const labels = [
    ...needs.tasks.map((task) => TASK_LABELS[task] ?? task),
    ...needs.requires.map((requirement) => REQUIREMENT_LABELS[requirement] ?? requirement),
  ]
  if (needs.priority !== "balanced") {
    labels.push(needs.priority === "speed" ? "Speed first" : "Quality first")
  }
  if (needs.local_only) labels.push("Local only")
  // « Images » et « Reads images » peuvent venir ensemble : une seule fois chaque étiquette.
  return [...new Set(labels)]
}

/** La clé d'un modèle utilisable tout de suite (« ollama/qwen3:8b »), sinon null. */
export function pickKey(pick: ModelPick): string | null {
  return pick.ready && pick.provider ? `${pick.provider}/${pick.model}` : null
}

/** La comparaison des modèles prêts du podium, sur la demande elle-même (au moins deux). */
export function compareHref(picks: ModelPick[], query: string): string | null {
  const keys = picks.map(pickKey).filter((key): key is string => key !== null)
  if (keys.length < 2) return null
  const params = new URLSearchParams()
  for (const key of keys) params.append("model", key)
  params.set("prompt", query)
  return `/compare?${params}`
}
