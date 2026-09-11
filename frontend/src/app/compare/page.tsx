import type { Metadata } from "next";
import { Suspense } from "react";

import { Compare } from "@/components/compare";

export const metadata: Metadata = {
  title: "Compare models · Netherbrain",
};

// Server Component : la page elle-même est statique, <Compare /> s'hydrate dans le navigateur.
// <Compare /> lit l'URL (?model=…&model=…) : il doit être entouré d'un <Suspense>.
export default function ComparePage() {
  return (
    <Suspense>
      <Compare />
    </Suspense>
  );
}
