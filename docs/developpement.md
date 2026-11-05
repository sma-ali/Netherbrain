# Développement

Lancer Netherbrain sans Docker, brancher des fournisseurs distants, lancer les tests, et la référence de l'API.

## Lancer sans Docker

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

## Fournisseurs distants (optionnel)

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

## Tests, lint et migrations

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

## API

| Méthode | Chemin        | Description                                                  |
|---------|---------------|--------------------------------------------------------------|
| GET     | `/api/health` | Sonde de vivacité                                            |
| GET     | `/api/models` | Modèles de tous les fournisseurs, et disponibilité de chacun |
| POST    | `/api/chat`   | Streame une réponse sans rien enregistrer                    |
| GET     | `/api/conversations` | Conversations, de la plus récemment active à la plus ancienne |
| POST    | `/api/conversations` | Crée une conversation (`{project_id}` facultatif)      |
| GET     | `/api/conversations/{id}` | Une conversation et ses messages                  |
| DELETE  | `/api/conversations/{id}` | Supprime une conversation et ses messages         |
| POST    | `/api/conversations/{id}/messages` | Envoie un message, streame et enregistre la réponse (`attachment_ids`, `agent`) |
| POST    | `/api/conversations/{id}/approvals/{call_id}` | Répond à l'agent : autorisation, ou réponse à sa question |
| GET     | `/api/conversations/{id}/attachments` | Fichiers joints à la conversation et leur état de lecture |
| POST    | `/api/conversations/{id}/attachments` | Joint un fichier (202 : lecture en tâche de fond)     |
| GET     | `/api/conversations/{id}/attachments/{attachment_id}/content` | L'image jointe, pour l'afficher |
| DELETE  | `/api/conversations/{id}/attachments/{attachment_id}` | Retire un fichier joint      |
| GET     | `/api/projects` | Projets, par ordre alphabétique (dossier, branche Git, consignes) |
| POST    | `/api/projects` | Crée un projet à partir d'un dossier (`{path, name}`)   |
| GET     | `/api/projects/{id}` | Un projet                                          |
| DELETE  | `/api/projects/{id}` | Oublie un projet (ses conversations et son dossier restent) |
| GET     | `/api/workspace/directories?path=` | Sous-dossiers du dossier personnel, pour choisir un projet |
| GET     | `/api/catalog` | Fiches des modèles (taille, contexte, capacités) et mesures réelles |
| POST    | `/api/advisor/recommend` | Recommande des modèles pour une demande (`{query}`), avec leurs raisons |
| GET     | `/api/advisor/benchmarks` | État des benchmarks en ligne : configurés, nombre de modèles, date |
| POST    | `/api/advisor/benchmarks/sync` | Met à jour les benchmarks tout de suite            |
| GET     | `/api/comparisons` | Comparaisons, de la plus récente à la plus ancienne     |
| POST    | `/api/comparisons` | Crée une comparaison (2 à 4 modèles)                    |
| GET     | `/api/comparisons/{id}` | Une comparaison et les réponses de chaque modèle   |
| DELETE  | `/api/comparisons/{id}` | Supprime une comparaison                           |
| POST    | `/api/comparisons/{id}/results/{result_id}/run` | Streame et enregistre la réponse d'un modèle |

Les deux routes de streaming émettent des événements `reasoning` et `token`, puis un événement
final `done` portant les métriques (`ttft_ms`, `total_ms`, `tokens_per_second`...) ou un
événement `error`. En mode agent s'y ajoutent `tool_call`, `tool_request` (le stream attend
alors votre autorisation, envoyée par une autre requête) et `tool_result`.

- `/api/chat` reçoit toute la conversation (`{provider, model, messages}`) et n'enregistre rien.
  L'interface s'en sert quand l'historique est indisponible.
- `/api/conversations/{id}/messages` ne reçoit que le nouveau message (`{provider, model, content}`) :
  le serveur reconstitue l'historique depuis la base. Si le client se déconnecte en pleine
  réponse, ce qui a déjà été généré est tout de même enregistré.
