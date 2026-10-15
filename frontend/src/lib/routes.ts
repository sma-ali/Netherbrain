/** Les adresses du chat : une par conversation, et une nouvelle conversation, dans un projet ou non. */

const CONVERSATION = /^\/c\/([^/]+)\/?$/

/** L'identifiant de la conversation dans l'adresse (/c/<id>), ou null. */
export function conversationIdFromPath(pathname: string): string | null {
  const match = CONVERSATION.exec(pathname)
  return match ? decodeURIComponent(match[1]) : null
}

/** L'adresse d'une conversation ; sans conversation, celle d'une nouvelle (?project=<id>). */
export function chatPath(conversationId: string | null, projectId: string | null = null): string {
  if (conversationId) return `/c/${encodeURIComponent(conversationId)}`
  return projectId ? `/?project=${encodeURIComponent(projectId)}` : "/"
}
