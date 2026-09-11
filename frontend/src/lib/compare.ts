import type { ChatMetrics, ModelInfo } from "@/lib/api"

/**
 * Répartit les modèles à comparer.
 *
 * Les modèles locaux partagent le même GPU : lancés ensemble, ils se disputeraient la VRAM
 * et fausseraient les mesures. Ils passent donc un par un (`sequential`), tandis que les
 * modèles distants partent tous en même temps (`parallel`).
 */
export function planRuns(models: ModelInfo[], localProviders: Set<string>) {
  return {
    sequential: models.filter((model) => localProviders.has(model.provider)),
    parallel: models.filter((model) => !localProviders.has(model.provider)),
  }
}

export type ComparedMetric = "ttft_ms" | "tokens_per_second" | "total_ms"

// Pour chaque métrique : vaut-il mieux une valeur basse (durées) ou haute (vitesse) ?
const BETTER: Record<ComparedMetric, "lower" | "higher"> = {
  ttft_ms: "lower",
  tokens_per_second: "higher",
  total_ms: "lower",
}

/**
 * Pour chaque métrique, la clé du modèle qui s'en sort le mieux.
 * Une métrique n'a pas de gagnant si moins de deux modèles l'ont mesurée.
 */
export function findBest(
  results: { key: string; metrics?: ChatMetrics }[],
): Partial<Record<ComparedMetric, string>> {
  const best: Partial<Record<ComparedMetric, string>> = {}

  for (const metric of Object.keys(BETTER) as ComparedMetric[]) {
    const values = results.flatMap(({ key, metrics }) => {
      const value = metrics?.[metric]
      return typeof value === "number" ? [{ key, value }] : []
    })
    if (values.length < 2) continue

    const direction = BETTER[metric] === "lower" ? 1 : -1
    values.sort((a, b) => direction * (a.value - b.value))
    best[metric] = values[0].key
  }

  return best
}
