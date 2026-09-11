import type { Metadata } from "next";

import { Compare } from "@/components/compare";

export const metadata: Metadata = {
  title: "Compare models · Netherbrain",
};

// Server Component : la page elle-même est statique, <Compare /> s'hydrate dans le navigateur.
export default function ComparePage() {
  return <Compare />;
}
