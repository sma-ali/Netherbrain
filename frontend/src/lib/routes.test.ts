import { describe, expect, it } from "vitest"

import { chatPath, conversationIdFromPath } from "./routes"

const id = "01a0ac8c-c2f9-75be-84a2-ee72a8bf587f"

describe("conversation addresses", () => {
  it("reads the conversation from the address", () => {
    expect(conversationIdFromPath(`/c/${id}`)).toBe(id)
    expect(conversationIdFromPath(`/c/${id}/`)).toBe(id)
    expect(conversationIdFromPath("/")).toBeNull()
    expect(conversationIdFromPath("/compare")).toBeNull()
    expect(conversationIdFromPath(`/c/${id}/other`)).toBeNull()
  })

  it("writes the address of a conversation, or of a new one", () => {
    expect(chatPath(id)).toBe(`/c/${id}`)
    expect(chatPath(null)).toBe("/")
    expect(chatPath(null, "project-1")).toBe("/?project=project-1")
    // Une conversation existante a déjà son projet : l'adresse n'a pas à le répéter.
    expect(chatPath(id, "project-1")).toBe(`/c/${id}`)
  })

  it("round-trips", () => {
    expect(conversationIdFromPath(chatPath(id))).toBe(id)
  })
})
