import { BrainCircuit } from "lucide-react"
import type { ReactNode } from "react"

import { AppNav } from "@/components/app-nav"

/** La barre latérale commune : le nom, la navigation, puis le contenu propre à chaque page. */
export function Sidebar({ children }: { children?: ReactNode }) {
  return (
    // Masquée sur les petits écrans : chaque page affiche alors une navigation compacte.
    <aside className="hidden w-64 shrink-0 flex-col border-r bg-card/40 md:flex">
      <div className="flex items-center gap-2 px-4 py-3 font-semibold tracking-tight">
        <BrainCircuit className="size-5 text-primary" />
        Netherbrain
      </div>
      <AppNav className="px-3 pb-3" />
      {children}
    </aside>
  )
}
