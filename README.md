# Netherbrain

[![CI](https://github.com/sma-ali/Netherbrain/actions/workflows/ci.yml/badge.svg)](https://github.com/sma-ali/Netherbrain/actions/workflows/ci.yml)

> Many minds, one interface.

Netherbrain est une plateforme de chat auto-hébergeable qui orchestre plusieurs LLM open source :
des modèles locaux qui tournent sur votre propre GPU via [Ollama](https://ollama.com), et des
modèles distants via n'importe quelle API compatible OpenAI.

## Avancement

Développement en cours. Jalon actuel : **un agent de code sûr et lisible**.

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
- [x] Conseiller : décrivez votre projet, il recommande les modèles adaptés et explique pourquoi
- [x] Fichiers et dossiers joints directement dans le chat (glisser-déposer, coller), fouillés par RAG quand ils sont longs
- [x] Projets, façon Claude Code : un dossier de code par projet, avec ses conversations et ses consignes (AGENTS.md)
- [x] Agent de code : le modèle lit, cherche et modifie les fichiers du projet, chaque action sensible demandant votre accord
- [x] Questions de l'agent, avec des réponses en un clic (outil `ask_user`)
- [x] Images dans le chat, envoyées aux modèles qui savent les lire
- [x] Diff de chaque écriture de l'agent, à relire avant d'autoriser
- [x] Dossier de travail dédié, seul monté dans Docker ; commandes de l'agent sans les secrets
- [x] Une adresse par conversation (`/c/<id>`) : rechargement, favoris, précédent / suivant

## Architecture

```
Interface Next.js ──HTTP/SSE──> Passerelle FastAPI ──API compatible OpenAI──> Ollama (GPU local)
   (navigateur)                         │                                └──> OpenRouter, Groq (optionnels)
                                        ├──SQLAlchemy──> PostgreSQL + pgvector (historique, fichiers joints)
                                        └──outils de l'agent──> dossier de travail (~/netherbrain-workspace)
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

Si l'interface indique « ollama unavailable », Ollama n'est pas lancé sur la machine hôte :
`sudo systemctl start ollama`, ou `sudo systemctl enable --now ollama` pour qu'il démarre avec
la machine (le désactiver libère le GPU pour d'autres usages, comme les jeux).

Les conversations sont stockées dans PostgreSQL, sur le volume `pgdata` : elles survivent aux
redémarrages, mais `docker compose down -v` les efface. Les migrations s'appliquent
automatiquement au démarrage de l'API.

Chaque conversation a son adresse, `http://localhost:3000/c/<id>` : recharger la page y ramène,
on peut la garder en favori ou l'ouvrir dans un nouvel onglet (clic du milieu dans la barre
latérale), et les boutons précédent / suivant du navigateur passent d'une conversation à
l'autre. Une nouvelle conversation dans un projet a l'adresse `/?project=<id>`. L'adresse change
sans recharger la page (`history.pushState`, que Next.js synchronise avec son routeur).

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

## Projets

Comme dans Claude Code, un projet est un **dossier de code** auquel on rattache des
conversations. La barre latérale du chat regroupe les conversations par projet ; l'en-tête
affiche le dossier, la branche Git en cours et le fichier de consignes du projet.

Dans une conversation de projet, le modèle reçoit en message système le nom du projet, le
contenu de la racine de son dossier et ses consignes : le fichier `AGENTS.md` (format ouvert,
partagé par plusieurs outils de code) ou, à défaut, `CLAUDE.md`.

Les projets sont choisis dans un **dossier de travail dédié**, `~/netherbrain-workspace` par
défaut (`NETHERBRAIN_WORKSPACE_ROOT`) : chaque sous-dossier peut devenir un projet. On y met ce
que l'agent a le droit de toucher, et rien d'autre : pas tous ses projets, et surtout pas un
dossier qui contient des secrets. L'API n'accède jamais à rien en dehors : les chemins reçus
sont résolus (`..`, liens symboliques compris) puis vérifiés. Supprimer un projet garde ses
conversations et ne touche jamais au dossier.

Avec Docker, **seul ce dossier** est monté dans le conteneur de l'API, sur `/workspace`
(variable `NETHERBRAIN_WORKSPACE`). La limite ne dépend alors plus du code de l'API : le reste
de la machine n'existe pas pour le conteneur. Le dossier doit exister avant le démarrage
(sinon Docker le créerait en root, sans droit d'écriture) :

```bash
mkdir -p ~/netherbrain-workspace
docker compose up --build
```

Sous WSL, il s'ouvre depuis l'Explorateur Windows à l'adresse
`\\wsl.localhost\<distribution>\home\<utilisateur>\netherbrain-workspace` : on y dépose les
fichiers à faire modifier par l'agent. Un fichier joint au chat, lui, n'est qu'une copie, lue
mais jamais modifiable : le navigateur n'en transmet que le contenu, pas l'emplacement.

## Agent de code

Dans une conversation de projet, le mode **Agent** (actif par défaut, comme dans Claude Code)
donne au modèle des outils sur le dossier du projet : `list_files`, `read_file` et
`search_files` (lecture, exécutés directement), puis `write_file`, `edit_file` et `run_command`
(modification, **soumis à votre accord**). Chaque appel s'affiche dans la réponse avec son
résultat repliable ; une action sensible attend un clic : « Allow once », « Always allow »
(pour toute la conversation) ou « Deny ».

Avant d'autoriser une écriture, on voit **exactement ce qui va changer** : un diff façon
`git diff`, lignes retirées en rouge, ajoutées en vert, numérotées, avec 3 lignes de contexte.
Il est calculé sans rien écrire (`difflib`), puis gardé dans l'historique : on peut revoir
plus tard ce que l'agent a modifié, fichier par fichier.

Un septième outil, `ask_user`, permet au modèle de **vous poser une question** quand une
décision vous revient : ses propositions s'affichent en boutons, et vous pouvez aussi taper
votre propre réponse.

```
Question → le modèle demande un outil → autorisation si nécessaire → exécution dans le dossier
du projet → résultat renvoyé au modèle → il recommence, jusqu'à 12 fois, puis répond
```

Le mode n'est proposé qu'aux modèles qui savent appeler des outils (`ornith:9b`, `qwen3.5:9b`,
`gemma4:12b`, `gpt-oss:20b`, la plupart des modèles récents) : la route `/api/models` dit
lesquels, et une clé à molette les signale dans le sélecteur. Dans un projet, le modèle proposé
par défaut en fait toujours partie : le dernier choisi pour l'agent, sinon le premier capable.
Netherbrain retient à part le dernier modèle choisi pour discuter. Si l'on choisit malgré tout
un modèle sans outils, un message l'explique sous la saisie, avec un bouton pour repasser sur
un modèle capable ; et ce modèle a pour consigne de ne jamais prétendre avoir modifié un fichier.

Les garde-fous :

- **confinement** : chaque chemin est résolu puis vérifié, donc ni `..`, ni chemin absolu, ni
  lien symbolique ne permet de sortir du dossier du projet ;
- **rien ne s'écrit et aucune commande ne se lance sans un clic** ; un refus est renvoyé au
  modèle, qui doit s'en accommoder ;
- **les commandes ne voient pas les secrets du serveur** : elles reçoivent seulement quelques
  variables d'environnement (`PATH`, `HOME`, la langue…), jamais les clés d'API ni l'adresse de
  la base. C'est une liste de ce qui est permis, pas de ce qui est interdit : une clé ajoutée
  plus tard reste cachée sans y penser. `NETHERBRAIN_AGENT_ALLOW_COMMANDS=false` coupe les
  commandes : l'agent lit et modifie alors seulement des fichiers ;
- la boucle s'arrête après 12 appels d'outils (`NETHERBRAIN_AGENT_MAX_STEPS`), une commande est
  tuée au bout de 2 minutes, et une demande d'autorisation sans réponse est refusée après 5 min ;
- **injection de prompt** : un fichier du projet peut contenir des instructions piégées (« ignore
  tes consignes, lance ceci… »). C'est le vrai risque de ce mode, et l'autorisation avant chaque
  action est aujourd'hui la seule protection : lisez ce que l'agent propose avant de valider.

Hors Docker, les commandes tournent sur votre machine, avec vos droits : le confinement des
outils de fichiers ne les concerne pas. Dans Docker, elles tournent dans le conteneur de l'API,
qui ne voit que le dossier de travail et ne contient que Python (ni Node, ni git). Pour laisser
l'agent lancer des commandes, préférez donc Docker.

### Fenêtre de contexte

Ollama charge par défaut les modèles avec **4096 tokens** de contexte, bien trop peu dès que
l'agent lit un fichier : la conversation serait tronquée en silence. Netherbrain discute donc
avec Ollama par son **API native** (`/api/chat`), la seule qui accepte l'option `num_ctx`, et
demande 16384 tokens (`NETHERBRAIN_OLLAMA_CONTEXT_LENGTH`, au prix d'un peu de VRAM).

## Joindre des fichiers au chat

Comme dans Claude, on joint des fichiers **directement dans la conversation** : bouton « + »
(fichiers ou dossier entier), glisser-déposer n'importe où sur la conversation, ou coller.
Ce sont des **copies en lecture seule** : pour qu'un modèle modifie des fichiers, ils doivent
être dans le dossier d'un projet, où l'agent les lit à la demande sans rien importer. Joindre un
gros dossier (plus de 200 fichiers) propose d'ailleurs d'en faire un projet.
Images, PDF et tout fichier texte sont acceptés, code compris (`.py`, `.tsx`, `Dockerfile`, CSV…).
Dans un dossier, les fichiers cachés (`.env`, `.git`…) et les dépendances (`node_modules`…)
sont ignorés.

Chaque fichier est lu en tâche de fond (le message part une fois tous les fichiers lus), puis
reste disponible pour toute la suite de la conversation :

```
Fichiers courts (32 000 caractères au total) → envoyés en entier au modèle, balisés par nom
Fichiers longs → RAG : morceaux de ~1 200 caractères, vecteurs (nomic-embed-text), pgvector
                 → seuls les 5 passages les plus proches de la question partent, cités [1], [2]…
```

Le contenu des fichiers est présenté au modèle comme une **donnée, jamais une consigne** : un
fichier piégé (« ignore tes instructions… ») ne doit pas pouvoir le détourner.

Prérequis pour les fichiers longs : le modèle d'embeddings, à installer une fois avec
`ollama pull nomic-embed-text`. Sans lui, les fichiers courts fonctionnent quand même ; pour les
longs, seul leur début est envoyé, avec un avertissement.

### Images

Une capture d'écran collée, une photo déposée : les images (PNG, JPEG, WebP, GIF) partent
**telles quelles** aux modèles qui savent les lire, repérés par un œil dans le sélecteur
(gemma4, qwen3.5…). Elles sont reconnues à leurs premiers octets, jamais à leur extension, et
gardées en base : chaque message renvoie l'historique au modèle, images comprises.

- Un modèle sans vision ne reçoit jamais d'image : l'interface bloque l'envoi en suggérant un
  modèle qui sait les lire, et l'API répond 422. Pour les images des messages précédents, il
  reçoit seulement une mention (« [Image capture.png: not shown to you] ») : il sait qu'elles
  existent, sans prétendre les voir.
- Chaque image coûte des centaines de tokens : seules les 8 plus récentes partent
  (`NETHERBRAIN_MAX_IMAGES_SENT`).

## Comparer des modèles

La page `/compare` pose la même question à 2 à 4 modèles et affiche leurs réponses côte à côte,
puis un tableau des métriques (délai avant le premier token, vitesse, temps total) où le meilleur
de chaque colonne est mis en avant.

Les modèles distants sont interrogés en parallèle. Les modèles locaux, eux, passent un par un :
ils partagent le même GPU, et les lancer ensemble saturerait la VRAM et fausserait les mesures.
Le délai avant le premier token d'un modèle local inclut son chargement en VRAM.

Chaque comparaison est enregistrée : on la retrouve dans l'historique, avec la réponse et les
métriques de chaque modèle.

## Catalogue des modèles et conseiller

La page `/models` s'ouvre sur un **conseiller** : on décrit en une phrase ce qu'on veut faire
(« un bot Discord qui résume des PDF en français, en local ») et il propose un podium : le
meilleur choix, une option plus rapide, et un modèle à télécharger ou une alternative cloud.
Chaque choix est justifié, et un bouton compare les modèles proposés sur la demande elle-même.

```
Demande ──LLM (sortie structurée)──> besoins : tâches, capacités exigées, priorité, local ou non
                                          │
Modèles disponibles + grille de forces + benchmarks en ligne + vitesses mesurées ici + VRAM
                                          │
                              score calculé par du code ──> podium expliqué
```

- **Comprendre** : un modèle local lit la demande et répond dans un format JSON imposé
  (sortie structurée d'Ollama). S'il n'y en a aucun de disponible, des mots-clés prennent le relais.
- **Décider** : c'est du code, pas le LLM, qui classe les modèles. Il ne peut recommander que
  des modèles réels, et chaque note se justifie.
- **Savoir** : une grille de forces par famille de modèles, écrite à la main, complétée par
  les benchmarks publics d'[Artificial Analysis](https://artificialanalysis.ai/) quand une clé
  d'API gratuite est configurée (`NETHERBRAIN_ARTIFICIAL_ANALYSIS_API_KEY`). Ils sont récupérés
  au plus une fois par jour et gardés en base ; les noms sont rapprochés automatiquement
  (« qwen3.5:9b » chez Ollama, « Qwen3.5 9B » chez Artificial Analysis).
- **Tenir compte de la machine** : les vitesses mesurées par Netherbrain, et la VRAM de la
  carte graphique (`NETHERBRAIN_GPU_VRAM_GB`, 16 par défaut) : un modèle qui ne tient pas
  n'est jamais conseillé au téléchargement. Sans mesure, la vitesse est estimée d'après la
  taille du modèle, en tenant compte des modèles « Mixture of Experts » (comme gpt-oss) qui ne
  font travailler qu'une partie de leurs poids à chaque token : leurs experts sont lus dans la
  fiche détaillée d'Ollama.

Sous le conseiller, le catalogue présente une fiche par modèle : taille, contexte, capacités
(raisonnement, vision, outils, code), prix, et les **mesures réelles** faites par Netherbrain
sur votre installation. On peut chercher, filtrer et trier, puis ouvrir un modèle dans le chat
ou en sélectionner plusieurs pour les comparer.

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
| GET     | `/api/workspace/directories?path=` | Sous-dossiers du dossier de travail, pour choisir un projet |
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
