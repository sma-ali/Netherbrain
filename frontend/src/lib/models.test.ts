import { describe, expect, it } from "vitest"

import type { ModelInfo } from "./api"
import { EMPTY_MEMORY, defaultModel, modelKey, rememberPick } from "./models"

// Dans l'ordre de l'API : alphabétique, et le premier ne sait pas utiliser d'outils.
const deepseek: ModelInfo = { id: "deepseek-r1:14b", provider: "ollama" }
const gemma: ModelInfo = { id: "gemma4:12b", provider: "ollama", tools: true, vision: true }
const gptOss: ModelInfo = { id: "gpt-oss:20b", provider: "ollama", tools: true }
const models = [deepseek, gemma, gptOss]

describe("defaultModel", () => {
  it("never proposes a model without tools for the agent", () => {
    expect(defaultModel(models, false, EMPTY_MEMORY)).toBe(deepseek)
    expect(defaultModel(models, true, EMPTY_MEMORY)).toBe(gemma)
  })

  it("comes back to the last model chosen for each use", () => {
    const memory = { chat: modelKey(deepseek), agent: modelKey(gptOss) }

    expect(defaultModel(models, false, memory)).toBe(deepseek)
    expect(defaultModel(models, true, memory)).toBe(gptOss)
  })

  it("forgets a remembered model that is gone", () => {
    const memory = { chat: "ollama/removed:7b", agent: "ollama/removed:7b" }

    expect(defaultModel(models, false, memory)).toBe(deepseek)
    expect(defaultModel(models, true, memory)).toBe(gemma)
  })

  it("falls back to any model when none can use tools", () => {
    expect(defaultModel([deepseek], true, EMPTY_MEMORY)).toBe(deepseek)
    expect(defaultModel([], true, EMPTY_MEMORY)).toBeNull()
  })
})

describe("rememberPick", () => {
  it("remembers the choice for the use it was made in", () => {
    expect(rememberPick(EMPTY_MEMORY, deepseek, false)).toEqual({
      chat: "ollama/deepseek-r1:14b",
      agent: null,
    })
    expect(rememberPick(EMPTY_MEMORY, gptOss, true)).toEqual({
      chat: null,
      agent: "ollama/gpt-oss:20b",
    })
  })

  it("does not remember a model without tools for the agent", () => {
    const memory = { chat: null, agent: modelKey(gemma) }

    expect(rememberPick(memory, deepseek, true)).toBe(memory)
  })
})
