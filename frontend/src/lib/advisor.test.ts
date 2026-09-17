import { describe, expect, it } from "vitest"

import { compareHref, describeNeeds, pickKey } from "./advisor"
import type { ModelPick } from "./api"
import { formatAge } from "./format"

const pick = (model: string, ready = true, provider: string | null = "ollama"): ModelPick => ({
  role: "best",
  provider,
  model,
  local: true,
  ready,
  score: 1,
  reasons: [],
  warnings: [],
  pull_command: ready ? null : `ollama pull ${model}`,
  benchmark: null,
})

describe("describeNeeds", () => {
  it("lists tasks, requirements, priority and privacy", () => {
    expect(
      describeNeeds({
        tasks: ["summary", "multilingual"],
        requires: ["long_context"],
        priority: "speed",
        local_only: true,
      }),
    ).toEqual(["Long documents", "Other languages", "Long context", "Speed first", "Local only"])
  })
})

describe("compareHref", () => {
  it("compares the ready models on the request itself", () => {
    const href = compareHref([pick("a"), pick("b"), pick("c", false, null)], "coder une API")

    expect(href).toBe("/compare?model=ollama%2Fa&model=ollama%2Fb&prompt=coder+une+API")
  })

  it("needs at least two ready models", () => {
    expect(compareHref([pick("a"), pick("b", false, null)], "x")).toBeNull()
    expect(pickKey(pick("b", false, null))).toBeNull()
  })
})

describe("formatAge", () => {
  it("says how long ago, in the largest sensible unit", () => {
    const now = Date.parse("2026-09-16T12:00:00Z")

    expect(formatAge("2026-09-16T11:59:40Z", now)).toBe("just now")
    expect(formatAge("2026-09-16T11:55:00Z", now)).toBe("5 min ago")
    expect(formatAge("2026-09-16T09:00:00Z", now)).toBe("3 h ago")
    expect(formatAge("2026-09-14T12:00:00Z", now)).toBe("2 days ago")
  })
})
