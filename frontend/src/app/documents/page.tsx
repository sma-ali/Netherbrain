import type { Metadata } from "next";

import { DocumentsLibrary } from "@/components/documents-library";

export const metadata: Metadata = {
  title: "Documents · Netherbrain",
};

export default function DocumentsPage() {
  return <DocumentsLibrary />;
}
