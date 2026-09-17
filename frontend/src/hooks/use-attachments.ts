import { useCallback, useEffect, useRef, useState } from "react"

import { deleteAttachment, listAttachments, uploadAttachment } from "@/lib/api"
import {
  fromAttachmentInfo,
  runPool,
  type AttachmentItem,
  type PickedFile,
} from "@/lib/attachments"

/** Les fichiers joints qui attendent dans la zone de saisie : envoi, lecture, retrait. */
export function useAttachments() {
  const [items, setItems] = useState<AttachmentItem[]>([])
  // La conversation où partent les fichiers : elle est créée au premier fichier joint.
  const [conversationId, setConversationId] = useState<string | null>(null)
  // Fichiers retirés pendant leur envoi : à supprimer du serveur dès qu'il a répondu.
  const removedRef = useRef(new Set<string>())

  const reading = items.some((item) => item.status === "processing")

  // Tant que le serveur lit des fichiers, on redemande leur état toutes les 1,5 s (« polling »).
  useEffect(() => {
    if (!reading || conversationId === null) return
    const timer = setInterval(() => {
      listAttachments(conversationId)
        .then((saved) => {
          const byId = new Map(saved.map((attachment) => [attachment.id, attachment]))
          setItems((prev) =>
            prev.map((item) => {
              const fresh = byId.get(item.id)
              return fresh ? { ...item, status: fresh.status, error: fresh.error } : item
            }),
          )
        })
        .catch(() => {}) // on réessaiera au prochain tour
    }, 1500)
    return () => clearInterval(timer)
  }, [reading, conversationId])

  /** Envoie les fichiers, trois à la fois, dans la conversation (créée si besoin). */
  const add = useCallback(
    async (picked: PickedFile[], ensureConversation: () => Promise<string>) => {
      if (picked.length === 0) return
      const locals: AttachmentItem[] = picked.map(({ file, path }) => ({
        id: `local-${crypto.randomUUID()}`,
        name: file.name,
        path: path ?? null,
        size: file.size,
        status: "uploading",
        // Une image s'affiche comme telle dès l'envoi, avant même la réponse du serveur.
        contentType: file.type || null,
      }))
      setItems((prev) => [...prev, ...locals])

      let id: string
      try {
        id = await ensureConversation()
      } catch (error) {
        const message = errorText(error)
        const failed = new Set(locals.map((local) => local.id))
        setItems((prev) =>
          prev.map((item) =>
            failed.has(item.id) ? { ...item, status: "error", error: message } : item,
          ),
        )
        return
      }
      setConversationId(id)

      await runPool(
        picked.map((pick, index) => async () => {
          const local = locals[index].id
          try {
            const saved = await uploadAttachment(id, pick.file, pick.path)
            if (removedRef.current.delete(local)) {
              await deleteAttachment(id, saved.id).catch(() => {})
              return
            }
            setItems((prev) => update(prev, local, fromAttachmentInfo(saved)))
          } catch (error) {
            setItems((prev) => update(prev, local, { status: "error", error: errorText(error) }))
          }
        }),
        3,
      )
    },
    [],
  )

  const remove = useCallback(
    (ids: string[]) => {
      setItems((prev) => prev.filter((item) => !ids.includes(item.id)))
      for (const id of ids) {
        if (id.startsWith("local-")) removedRef.current.add(id)
        else if (conversationId !== null) void deleteAttachment(conversationId, id).catch(() => {})
      }
    },
    [conversationId],
  )

  /** Vide la zone de saisie : à l'envoi du message, ou en changeant de conversation. */
  const clear = useCallback(() => setItems([]), [])

  return {
    items,
    // Prêts à partir avec le prochain message.
    ready: items.filter((item) => item.status === "ready"),
    // Un envoi ou une lecture en cours : il faut attendre pour envoyer le message.
    busy: items.some((item) => item.status === "uploading" || item.status === "processing"),
    add,
    remove,
    clear,
  }
}

function update(items: AttachmentItem[], id: string, changes: Partial<AttachmentItem>) {
  return items.map((item) => (item.id === id ? { ...item, ...changes } : item))
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
