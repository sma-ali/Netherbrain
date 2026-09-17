"use client"

import type { FileDiff } from "@/lib/api"
import { parseDiff, type DiffRow } from "@/lib/diff"
import { cn } from "@/lib/utils"

const SIGNS: Record<DiffRow["kind"], string> = { hunk: "", add: "+", remove: "-", context: " " }

/** Un diff à relire : lignes retirées en rouge, ajoutées en vert, avec leurs numéros. */
export function DiffView({ diff, className }: { diff: FileDiff; className?: string }) {
  const rows = parseDiff(diff.lines)

  return (
    <div className={cn("overflow-hidden rounded-md border", className)}>
      <div className="flex items-center gap-2 border-b bg-muted/50 px-2 py-1 text-xs">
        <span className="truncate font-mono">{diff.path}</span>
        {diff.created && (
          <span className="shrink-0 rounded bg-emerald-500/15 px-1.5 text-emerald-700 dark:text-emerald-400">
            new file
          </span>
        )}
        <DiffStats diff={diff} className="ml-auto" />
      </div>
      {rows.length === 0 ? (
        <p className="px-2 py-1.5 text-xs text-muted-foreground">
          No change: the file stays the same.
        </p>
      ) : (
        <div className="max-h-80 overflow-auto">
          <table className="w-full border-collapse font-mono text-xs leading-5">
            <tbody>
              {rows.map((row, index) =>
                row.kind === "hunk" ? (
                  <tr key={index} className="bg-sky-500/10 text-muted-foreground">
                    <td colSpan={3} className="px-2 select-none">
                      {row.text}
                    </td>
                  </tr>
                ) : (
                  <tr
                    key={index}
                    className={cn(
                      row.kind === "add" && "bg-emerald-500/15",
                      row.kind === "remove" && "bg-red-500/15",
                    )}
                  >
                    <td className="w-10 px-1 text-right text-muted-foreground/70 select-none">
                      {row.oldLine ?? ""}
                    </td>
                    <td className="w-10 px-1 text-right text-muted-foreground/70 select-none">
                      {row.newLine ?? ""}
                    </td>
                    <td className="px-2 whitespace-pre">
                      {/* Le signe ne se copie pas avec le code sélectionné. */}
                      <span className="text-muted-foreground select-none">{SIGNS[row.kind]}</span>
                      {row.text}
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
      {diff.truncated && (
        <p className="border-t px-2 py-1 text-xs text-muted-foreground">
          Too long: only the beginning of the diff is shown.
        </p>
      )}
    </div>
  )
}

/** Le nombre de lignes ajoutées et retirées, comme sur GitHub : +12 −3. */
export function DiffStats({ diff, className }: { diff: FileDiff; className?: string }) {
  return (
    <span className={cn("shrink-0 font-mono text-xs", className)}>
      <span className="text-emerald-600 dark:text-emerald-400">+{diff.added}</span>{" "}
      <span className="text-red-600 dark:text-red-400">−{diff.removed}</span>
    </span>
  )
}
