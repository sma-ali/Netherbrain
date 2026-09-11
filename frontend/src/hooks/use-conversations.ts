import { useCallback, useEffect, useState } from "react"

import { deleteConversation, listConversations, type ConversationSummary } from "@/lib/api"

interface ConversationsState {
  // "error" : l'historique est indisponible (base de données en panne, par exemple).
  status: "loading" | "ready" | "error"
  conversations: ConversationSummary[]
}

/** La liste des conversations enregistrées, de la plus récemment active à la plus ancienne. */
export function useConversations() {
  const [state, setState] = useState<ConversationsState>({ status: "loading", conversations: [] })
  const [version, setVersion] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    listConversations(controller.signal)
      .then((conversations) => setState({ status: "ready", conversations }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error", conversations: [] })
      })
    // Nettoyage : annule la requête si le composant disparaît ou recharge avant la réponse.
    return () => controller.abort()
  }, [version])

  // Recharge la liste ; l'ancienne reste affichée pendant ce temps (pas de clignotement).
  const refresh = useCallback(() => setVersion((n) => n + 1), [])

  const remove = useCallback(async (id: string) => {
    await deleteConversation(id)
    setState((prev) => ({
      ...prev,
      conversations: prev.conversations.filter((conversation) => conversation.id !== id),
    }))
  }, [])

  return { ...state, refresh, remove }
}
