import { Suspense } from "react";

import { Chat } from "@/components/chat";

// Server Component : génère la coquille statique, le <Chat /> interactif s'hydrate dans le navigateur.
// <Chat /> lit l'URL (?model=…) : Next.js demande alors de l'entourer d'un <Suspense>.
export default function Home() {
  return (
    <Suspense>
      <Chat />
    </Suspense>
  );
}
