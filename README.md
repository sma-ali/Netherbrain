# Netherbrain

[![CI](https://github.com/sma-ali/Netherbrain/actions/workflows/ci.yml/badge.svg)](https://github.com/sma-ali/Netherbrain/actions/workflows/ci.yml)

> Many minds, one interface.

Netherbrain est une plateforme de chat auto-hébergeable qui orchestre plusieurs LLM open source :
des modèles locaux qui tournent sur votre propre GPU via [Ollama](https://ollama.com), et des
modèles distants via n'importe quelle API compatible OpenAI.

## Avancement

Développement en cours. Jalon actuel : **catalogue des modèles**.

- [x] Passerelle FastAPI qui streame les réponses d'Ollama (Server-Sent Events)
- [x] Réflexion des modèles de raisonnement streamée à part de la réponse
- [x] Métriques par réponse : délai avant le premier token, tokens par seconde
- [x] Interface de chat Next.js : choix du modèle, réponses en Markdown, réflexion repliable, bouton stop
- [x] Plusieurs fournisseurs (Ollama, OpenRouter, Groq), avec dégradation gracieuse hors ligne
- [x] Docker Compose (images multi-étapes, non-root) et CI GitHub Actions
- [x] Conversations enregistrées dans PostgreSQL (migrations Alembic), réponse partielle conservée si on coupe
- [ ] Authentification
- [x] Comparaison de 2 à 4 modèles côte à côte, avec tableau des métriques et historique
- [x] Catalogue des modèles : filtres, tris et mesures réelles faites sur votre installation
- [ ] RAG sur vos propres documents

## Architecture

```
Interface Next.js ──HTTP/SSE──> Passerelle FastAPI ──API compatible OpenAI──> Ollama (GPU local)
   (navigateur)                         │                                └──> OpenRouter, Groq (optionnels)
                                        └──SQLAlchemy──> PostgreSQL (historique)
```

| Dossier     | Stack                                                                            |
|-------------|----------------------------------------------------------------------------------|
| `backend/`  | Python 3.14, FastAPI, Pydantic, SQLAlchemy 2 (async), Alembic, SDK OpenAI, uv, pytest, Ruff |
| base        | PostgreSQL 18 (image avec pgvector)                                              |
| `frontend/` | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Vitest |

La couche API ne dépend que d'une interface `LLMProvider` : tous les backends qui parlent l'API
Chat Completions d'OpenAI sont gérés par une seule classe, `OpenAICompatibleProvider`.
Le navigateur lit le stream SSE depuis la réponse d'un `fetch`, avec un petit parseur incrémental
(`EventSource` ne gère que les requêtes GET).

## Démarrage

### Avec Docker

Prérequis : Docker avec Compose, et [Ollama](https://ollama.com) qui tourne sur la machine hôte
avec au moins un modèle (`ollama pull qwen3:8b`).

```bash
docker compose up --build
```

Puis ouvrir <http://localhost:3000>.

Les conversations sont stockées dans PostgreSQL, sur le volume `pgdata` : elles survivent aux
redémarrages, mais `docker compose down -v` les efface. Les migrations s'appliquent
automatiquement au démarrage de l'API.

Le conteneur de l'API joint Ollama via `host.docker.internal`. Sous Linux, Ollama n'écoute par
défaut que sur `127.0.0.1`, que les conteneurs ne peuvent pas joindre : définissez
`OLLAMA_HOST=0.0.0.0` dans l'environnement du service Ollama. Si Ollama reste injoignable,
l'interface le signale comme indisponible et les fournisseurs distants continuent de fonctionner.

### Sans Docker (développement)

Prérequis : [uv](https://docs.astral.sh/uv/), Node.js 24+, Docker (pour PostgreSQL) et
[Ollama](https://ollama.com) qui tourne avec au moins un modèle.

```bash
# Terminal 1 : la base (dans Docker), puis l'API sur http://localhost:8000
docker compose up -d db      # seulement le service PostgreSQL
cd backend
uv sync                      # crée l'environnement virtuel et installe les dépendances
uv run alembic upgrade head  # crée ou met à jour les tables
uv run uvicorn netherbrain.main:app --reload
```

```bash
# Terminal 2 : interface sur http://localhost:3000
cd frontend
npm install
npm run dev
```

Documentation interactive de l'API : <http://localhost:8000/docs>

```bash
curl -N localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"provider": "ollama", "model": "qwen3:8b", "messages": [{"role": "user", "content": "Bonjour !"}]}'
```

### Fournisseurs distants (optionnel)

Les modèles locaux fonctionnent immédiatement, même hors ligne. Pour ajouter des modèles
distants, copiez la configuration d'exemple et collez vos clés d'API ; chaque fournisseur n'est
activé que si sa clé est renseignée :

```bash
cd backend
cp .env.example .env         # .env est ignoré par git
# NETHERBRAIN_OPENROUTER_API_KEY=...  -> https://openrouter.ai/keys (modèles gratuits par défaut)
# NETHERBRAIN_GROQ_API_KEY=...        -> https://console.groq.com/keys
```

Redémarrez l'API après avoir modifié `.env`. Si un fournisseur est injoignable (pas d'internet,
panne, clé invalide), il est signalé comme indisponible et tous les autres modèles continuent de
fonctionner.

### Développement

```bash
cd backend
uv run pytest                # tests (ni GPU ni réseau nécessaires : les fournisseurs sont simulés)
uv run ruff check .          # lint
uv run ruff format .         # formatage
```

Les tests utilisent SQLite en mémoire par défaut. La CI les relance sur un vrai PostgreSQL ;
pour faire pareil en local, définissez `NETHERBRAIN_TEST_DATABASE_URL` (même format que
`NETHERBRAIN_DATABASE_URL`, sur une base dédiée aux tests).

Après une modification des modèles (`db/models.py`), générez la migration, puis relisez-la :

```bash
uv run alembic revision --autogenerate -m "description du changement"
```

```bash
cd frontend
npm test                     # tests unitaires (Vitest)
npm run lint                 # ESLint
npm run build                # build de production + vérification des types
```

## Comparer des modèles

La page `/compare` pose la même question à 2 à 4 modèles et affiche leurs réponses côte à côte,
puis un tableau des métriques (délai avant le premier token, vitesse, temps total) où le meilleur
de chaque colonne est mis en avant.

Les modèles distants sont interrogés en parallèle. Les modèles locaux, eux, passent un par un :
ils partagent le même GPU, et les lancer ensemble saturerait la VRAM et fausserait les mesures.
Le délai avant le premier token d'un modèle local inclut son chargement en VRAM.

Chaque comparaison est enregistrée : on la retrouve dans l'historique, avec la réponse et les
métriques de chaque modèle.

## Catalogue des modèles

La page `/models` présente une fiche par modèle : taille, contexte, capacités (raisonnement,
vision, outils, code), prix, et surtout les **mesures réelles** faites par Netherbrain sur votre
installation (nombre de réponses, vitesse moyenne, délai avant le premier token). On peut
chercher, filtrer et trier, puis ouvrir un modèle dans le chat ou en sélectionner plusieurs
pour les comparer.

Ollama décrit ses modèles via son API native (`/api/tags`) ; OpenRouter et Groq ajoutent leurs
propres champs à la liste standard au format OpenAI.

## API

| Méthode | Chemin        | Description                                                  |
|---------|---------------|--------------------------------------------------------------|
| GET     | `/api/health` | Sonde de vivacité                                            |
| GET     | `/api/models` | Modèles de tous les fournisseurs, et disponibilité de chacun |
| POST    | `/api/chat`   | Streame une réponse sans rien enregistrer                    |
| GET     | `/api/conversations` | Conversations, de la plus récemment active à la plus ancienne |
| POST    | `/api/conversations` | Crée une conversation                                  |
| GET     | `/api/conversations/{id}` | Une conversation et ses messages                  |
| DELETE  | `/api/conversations/{id}` | Supprime une conversation et ses messages         |
| POST    | `/api/conversations/{id}/messages` | Envoie un message, streame et enregistre la réponse |
| GET     | `/api/catalog` | Fiches des modèles (taille, contexte, capacités) et mesures réelles |
| GET     | `/api/comparisons` | Comparaisons, de la plus récente à la plus ancienne     |
| POST    | `/api/comparisons` | Crée une comparaison (2 à 4 modèles)                    |
| GET     | `/api/comparisons/{id}` | Une comparaison et les réponses de chaque modèle   |
| DELETE  | `/api/comparisons/{id}` | Supprime une comparaison                           |
| POST    | `/api/comparisons/{id}/results/{result_id}/run` | Streame et enregistre la réponse d'un modèle |

Les deux routes de streaming émettent des événements `reasoning` et `token`, puis un événement
final `done` portant les métriques (`ttft_ms`, `total_ms`, `tokens_per_second`...) ou un
événement `error`.

- `/api/chat` reçoit toute la conversation (`{provider, model, messages}`) et n'enregistre rien.
  L'interface s'en sert quand l'historique est indisponible.
- `/api/conversations/{id}/messages` ne reçoit que le nouveau message (`{provider, model, content}`) :
  le serveur reconstitue l'historique depuis la base. Si le client se déconnecte en pleine
  réponse, ce qui a déjà été généré est tout de même enregistré.
