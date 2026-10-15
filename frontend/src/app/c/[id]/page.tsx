import { Suspense } from "react";

import { Chat } from "@/components/chat";

// La même page que l'accueil : <Chat /> lit l'identifiant dans l'adresse (/c/<id>) et ouvre
// la conversation. Recharger la page, ou la garder en favori, y ramène donc directement.
export default function ConversationPage() {
  return (
    <Suspense>
      <Chat />
    </Suspense>
  );
}
