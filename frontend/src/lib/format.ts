/** Durée en millisecondes affichée en secondes : 1234 → "1.2 s". */
export const formatSeconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`
