import { describe, expect, it } from "vitest"

import type { ModelCard } from "./api"
import { filterModels, sortModels } from "./catalog"

const card = (overrides: Partial<ModelCard>): ModelCard => ({
  id: "model",
  provider: "provider",
  local: false,
  name: "model",
  description: null,
  family: null,
  parameters_b: null,
  quantization: null,
  size_bytes: null,
  context_length: null,
  capabilities: [],
  free: null,
  stats: null,
  ...overrides,
})

const QWEN = card({
  id: "qwen3:8b",
  name: "qwen3:8b",
  provider: "ollama",
  local: true,
  free: true,
  capabilities: ["reasoning", "tools"],
  stats: { answers: 12, avg_ttft_ms: 400, avg_tokens_per_second: 110 },
})
const GEMMA = card({
  id: "google/gemma:free",
  name: "Google: Gemma",
  provider: "openrouter",
  free: true,
  capabilities: ["vision"],
  description: "A multimodal model",
  stats: { answers: 3, avg_ttft_ms: 900, avg_tokens_per_second: 150 },
})
const PAID = card({ id: "gpt", name: "GPT", provider: "openrouter", free: false })

const ids = (cards: ModelCard[]) => cards.map((c) => c.id)

describe("filterModels", () => {
  it("cumule les filtres cochés", () => {
    expect(ids(filterModels([QWEN, GEMMA, PAID], "", new Set(["free", "reasoning"])))).toEqual([
      "qwen3:8b",
    ])
  })

  it("cherche dans le nom, l'identifiant, le fournisseur et la description", () => {
    expect(ids(filterModels([QWEN, GEMMA, PAID], "MULTIMODAL", new Set()))).toEqual([
      "google/gemma:free",
    ])
    expect(ids(filterModels([QWEN, GEMMA, PAID], "ollama", new Set()))).toEqual(["qwen3:8b"])
  })

  it("sépare les modèles locaux et distants", () => {
    expect(ids(filterModels([QWEN, GEMMA, PAID], "", new Set(["remote"])))).toEqual([
      "google/gemma:free",
      "gpt",
    ])
  })
})

describe("sortModels", () => {
  it("met les plus rapides en tête et les modèles jamais essayés à la fin", () => {
    expect(ids(sortModels([PAID, QWEN, GEMMA], "speed"))).toEqual([
      "google/gemma:free",
      "qwen3:8b",
      "gpt",
    ])
  })

  it("classe par nombre de réponses", () => {
    expect(ids(sortModels([GEMMA, PAID, QWEN], "usage"))).toEqual([
      "qwen3:8b",
      "google/gemma:free",
      "gpt",
    ])
  })

  it("trie par nom", () => {
    expect(ids(sortModels([QWEN, PAID, GEMMA], "name"))).toEqual([
      "google/gemma:free",
      "gpt",
      "qwen3:8b",
    ])
  })
})
