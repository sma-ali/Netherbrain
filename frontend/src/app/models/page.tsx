import type { Metadata } from "next";

import { ModelsCatalog } from "@/components/models-catalog";

export const metadata: Metadata = {
  title: "Models · Netherbrain",
};

export default function ModelsPage() {
  return <ModelsCatalog />;
}
