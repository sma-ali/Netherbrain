/** Durée en millisecondes affichée en secondes : 1234 → "1.2 s". */
export const formatSeconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`

/** Grand nombre abrégé : 40960 → "41K", 1048576 → "1M". */
export function formatCount(value: number): string {
  if (value >= 1_000_000) return `${+(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${Math.round(value / 1_000)}K`
  return String(value)
}

/** Taille en octets, en unités décimales comme Ollama : 5225388164 → "5.2 GB". */
export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"]
  let value = bytes
  let unit = 0
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000
    unit++
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`
}
