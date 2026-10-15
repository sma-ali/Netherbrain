/** Lire un diff unifié (le format de `git diff`) pour l'afficher ligne à ligne, numéros compris. */

import type { AgentStep, FileDiff } from "@/lib/api"

export interface DiffRow {
  // hunk : en-tête d'un bloc ; add : ligne ajoutée ; remove : retirée ; context : inchangée.
  kind: "hunk" | "add" | "remove" | "context"
  text: string
  // Le numéro de la ligne avant et après la modification ; null si elle n'existe que d'un côté.
  oldLine: number | null
  newLine: number | null
}

// « @@ -12,5 +12,7 @@ » : le bloc commence ligne 12 avant (sur 5 lignes), ligne 12 après (sur 7).
const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/

export function parseDiff(lines: string[]): DiffRow[] {
  const rows: DiffRow[] = []
  let oldLine = 0
  let newLine = 0
  for (const line of lines) {
    const hunk = HUNK.exec(line)
    if (hunk) {
      oldLine = Number(hunk[1])
      newLine = Number(hunk[2])
      rows.push({ kind: "hunk", text: line, oldLine: null, newLine: null })
    } else if (line.startsWith("+")) {
      rows.push({ kind: "add", text: line.slice(1), oldLine: null, newLine: newLine++ })
    } else if (line.startsWith("-")) {
      rows.push({ kind: "remove", text: line.slice(1), oldLine: oldLine++, newLine: null })
    } else {
      // Une ligne de contexte existe des deux côtés : les deux compteurs avancent.
      rows.push({ kind: "context", text: line.slice(1), oldLine: oldLine++, newLine: newLine++ })
    }
  }
  return rows
}

/** Les fichiers modifiés par une étape de l'agent, quel que soit le format enregistré. */
export function stepDiffs(step: AgentStep): FileDiff[] {
  return step.diffs ?? (step.diff ? [step.diff] : [])
}

/** Le bilan de plusieurs fichiers : lignes ajoutées et retirées, au total. */
export function totalChanges(diffs: FileDiff[]): { added: number; removed: number } {
  return diffs.reduce(
    (total, diff) => ({ added: total.added + diff.added, removed: total.removed + diff.removed }),
    { added: 0, removed: 0 },
  )
}
