import { describe, expect, it } from "vitest"

import type { ChatMetrics } from "./api"
import { findBest, planRuns } from "./compare"

const metrics = (overrides: Partial<ChatMetrics>): ChatMetrics => ({
  total_ms: 1000,
  ttft_ms: 100,
  tokens_per_second: 50,
  ...overrides,
})

describe("planRuns", () => {
  it("lance les modèles locaux un par un et les distants en parallèle", () => {
    const models = [
      { id: "qwen3:8b", provider: "ollama" },
      { id: "gemma", provider: "openrouter" },
      { id: "llama3", provider: "ollama" },
      { id: "kimi", provider: "groq" },
    ]

    const plan = planRuns(models, new Set(["ollama"]))

    expect(plan.sequential.map((m) => m.id)).toEqual(["qwen3:8b", "llama3"])
    expect(plan.parallel.map((m) => m.id)).toEqual(["gemma", "kimi"])
  })
})

describe("findBest", () => {
  it("retient la durée la plus basse et la vitesse la plus haute", () => {
    const best = findBest([
      { key: "a", metrics: metrics({ ttft_ms: 300, tokens_per_second: 80, total_ms: 5000 }) },
      { key: "b", metrics: metrics({ ttft_ms: 120, tokens_per_second: 40, total_ms: 9000 }) },
    ])

    expect(best).toEqual({ ttft_ms: "b", tokens_per_second: "a", total_ms: "a" })
  })

  it("ignore les modèles sans mesure", () => {
    const best = findBest([
      { key: "a", metrics: metrics({ tokens_per_second: null }) },
      { key: "b", metrics: metrics({ tokens_per_second: 30 }) },
      { key: "c" },
    ])

    expect(best.tokens_per_second).toBeUndefined()
    expect(best.total_ms).toBe("a")
  })

  it("ne désigne aucun gagnant avec un seul résultat", () => {
    expect(findBest([{ key: "a", metrics: metrics({}) }])).toEqual({})
  })
})
