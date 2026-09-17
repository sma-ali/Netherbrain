/** Choisir le modèle proposé par défaut, selon qu'on discute ou qu'on fait travailler l'agent. */

import type { ModelInfo } from "@/lib/api"

/** Clé unique d'un modèle, tous fournisseurs confondus. Un nom de fournisseur ne contient jamais "/". */
export const modelKey = (model: ModelInfo) => `${model.provider}/${model.id}`

/** Les derniers modèles choisis : l'un pour discuter, l'autre pour l'agent (dans un projet). */
export interface ModelMemory {
  chat: string | null
  agent: string | null
}

export const EMPTY_MEMORY: ModelMemory = { chat: null, agent: null }

/**
 * Le modèle proposé tant que l'utilisateur n'en a pas choisi pour cette conversation.
 *
 * Pour l'agent : le dernier choisi pour lui s'il sait toujours utiliser des outils, sinon le
 * premier qui le sait (les modèles locaux sont en tête). Jamais, par défaut, un modèle qui
 * rendrait le mode agent impossible : c'était le piège du premier modèle par ordre alphabétique.
 */
export function defaultModel(
  models: ModelInfo[],
  agent: boolean,
  memory: ModelMemory,
): ModelInfo | null {
  const remembered = models.find((model) => modelKey(model) === memory[agent ? "agent" : "chat"])
  if (!agent) return remembered ?? models[0] ?? null
  if (remembered?.tools) return remembered
  return models.find((model) => model.tools) ?? models[0] ?? null
}

/** Ce qu'il faut retenir après un choix de modèle. */
export function rememberPick(memory: ModelMemory, picked: ModelInfo, agent: boolean): ModelMemory {
  // Un modèle sans outils choisi dans un projet vaut pour cette fois seulement : le retenir
  // ramènerait le piège à la conversation suivante.
  if (agent && !picked.tools) return memory
  return { ...memory, [agent ? "agent" : "chat"]: modelKey(picked) }
}
