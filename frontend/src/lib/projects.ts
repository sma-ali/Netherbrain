import type { ConversationSummary, Project } from "@/lib/api"

export interface ConversationGroups {
  /** Les conversations de chaque projet, par identifiant de projet. */
  byProject: Map<string, ConversationSummary[]>
  /** Les conversations sans projet (ou d'un projet qui n'existe plus). */
  loose: ConversationSummary[]
}

/** Range chaque conversation sous son projet, en gardant leur ordre (la plus récente d'abord). */
export function groupConversations(
  conversations: ConversationSummary[],
  projects: Project[],
): ConversationGroups {
  const byProject = new Map<string, ConversationSummary[]>(projects.map((p) => [p.id, []]))
  const loose: ConversationSummary[] = []
  for (const conversation of conversations) {
    const group = conversation.project_id ? byProject.get(conversation.project_id) : undefined
    if (group) group.push(conversation)
    else loose.push(conversation)
  }
  return { byProject, loose }
}

export interface Crumb {
  name: string
  path: string
}

/** Les étapes d'un chemin relatif, pour un fil d'Ariane : "a/b" donne a, puis a/b. */
export function breadcrumbs(path: string): Crumb[] {
  const names = path.split("/").filter(Boolean)
  return names.map((name, index) => ({ name, path: names.slice(0, index + 1).join("/") }))
}

/** Le dernier élément d'un chemin : "/home/moi/Projects" donne "Projects". */
export function basename(path: string): string {
  return path.split("/").filter(Boolean).at(-1) ?? path
}
