import { describe, expect, it } from "vitest"

import type { ModelInfo } from "./api"
import {
  groupAttachments,
  groupStatus,
  imageBlocker,
  isIgnored,
  isImage,
  runPool,
  type AttachmentItem,
} from "./attachments"

const item = (
  id: string,
  path: string | null,
  status: AttachmentItem["status"] = "ready",
): AttachmentItem => ({ id, name: path?.split("/").at(-1) ?? id, path, size: 10, status })

describe("isIgnored", () => {
  it("skips hidden files and dependency folders", () => {
    expect(isIgnored("app/.env")).toBe(true)
    expect(isIgnored("app/.git/config")).toBe(true)
    expect(isIgnored("app/node_modules/react/index.js")).toBe(true)
    expect(isIgnored("app/src/main.py")).toBe(false)
  })
})

describe("groupAttachments", () => {
  it("groups the files of a folder and keeps single files apart", () => {
    const groups = groupAttachments([
      item("notes.md", null),
      item("2", "app/src/a.py"),
      item("3", "app/b.py"),
    ])

    expect(groups.map((group) => [group.label, group.folder, group.items.length])).toEqual([
      ["notes.md", false, 1],
      ["app", true, 2],
    ])
  })
})

describe("groupStatus", () => {
  it("is busy while one file is, and counts unreadable files", () => {
    expect(groupStatus([item("1", null), item("2", null, "processing")])).toEqual({
      status: "processing",
      errors: 0,
    })
    expect(groupStatus([item("1", null, "error"), item("2", null)])).toEqual({
      status: "ready",
      errors: 1,
    })
  })
})

describe("runPool", () => {
  it("never runs more tasks at once than asked", async () => {
    let running = 0
    let peak = 0
    const done: number[] = []
    const tasks = [1, 2, 3, 4, 5].map((n) => async () => {
      running += 1
      peak = Math.max(peak, running)
      await new Promise((resolve) => setTimeout(resolve, 5))
      running -= 1
      done.push(n)
    })

    await runPool(tasks, 2)

    expect(peak).toBe(2)
    expect(done.sort()).toEqual([1, 2, 3, 4, 5])
  })
})

describe("images", () => {
  const image = (status: AttachmentItem["status"] = "ready"): AttachmentItem => ({
    ...item("capture.png", null, status),
    contentType: "image/png",
  })
  const models: ModelInfo[] = [
    { id: "gpt-oss:20b", provider: "ollama" },
    { id: "gemma4:12b", provider: "ollama", vision: true },
  ]

  it("recognizes images by their type", () => {
    expect(isImage(image())).toBe(true)
    expect(isImage({ ...item("a.pdf", null), contentType: "application/pdf" })).toBe(false)
    expect(isImage(item("pending", null, "uploading"))).toBe(false)
  })

  it("blocks images for a model that cannot read them, and suggests one that can", () => {
    expect(imageBlocker([image()], models[0], models)).toBe(
      "gpt-oss:20b cannot read images: pick a model that can, like gemma4:12b",
    )
    expect(imageBlocker([image()], models[1], models)).toBeNull()
    expect(imageBlocker([item("notes.md", null)], models[0], models)).toBeNull()
    // Une image illisible ne partira pas : elle ne bloque rien.
    expect(imageBlocker([image("error")], models[0], models)).toBeNull()
    expect(imageBlocker([image()], models[0], [models[0]])).toBe(
      "gpt-oss:20b cannot read images, and no available model can",
    )
  })
})
