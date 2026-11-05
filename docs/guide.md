# Guide d'utilisation

Le détail de chaque fonctionnalité. Pour installer Netherbrain, voir le [README](../README.md).

## Lancer avec Docker

Prérequis : Docker avec Compose, et [Ollama](https://ollama.com) qui tourne sur la machine hôte
avec au moins un modèle (`ollama pull qwen3:8b`).

```bash
cp .env.example .env         # facultatif : mot de passe de la base, adresse d'Ollama
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

## Projets

Comme dans Claude Code, un projet est un **dossier de code** auquel on rattache des
conversations. La barre latérale du chat regroupe les conversations par projet ; l'en-tête
affiche le dossier, la branche Git en cours et le fichier de consignes du projet.

Dans une conversation de projet, le modèle reçoit en message système le nom du projet, le
contenu de la racine de son dossier et ses consignes : le fichier `AGENTS.md` (format ouvert,
partagé par plusieurs outils de code) ou, à défaut, `CLAUDE.md`.

Un projet peut être **n'importe quel dossier de votre dossier personnel**
(`NETHERBRAIN_ACCESS_ROOT`, `~` par défaut), comme dans Claude Code : rien à copier ni à
cloner. Avant de l'ajouter, une étape demande d'**approuver le dossier** et rappelle ce que
l'agent pourra y faire seul. L'API n'accède jamais à rien au-delà du dossier personnel : les
chemins reçus sont résolus (`..`, liens symboliques compris) puis vérifiés. Supprimer un projet
garde ses conversations et ne touche jamais au dossier.

Avec Docker, le dossier personnel est monté dans le conteneur de l'API **au même chemin** que
sur la machine : `/home/moi/Projects/heretic` désigne le même dossier des deux côtés. Rien
d'autre de la machine n'y est visible. Les projets créés avant ce changement, dans l'ancien
dossier de travail (`NETHERBRAIN_WORKSPACE_ROOT`, `~/netherbrain-workspace`), continuent de
marcher, à condition que ce dossier soit dans le dossier personnel : seul celui-ci est monté.

Un fichier joint au chat, lui, n'est qu'une copie, lue mais jamais modifiable : le navigateur
n'en transmet que le contenu, pas l'emplacement.

## Agent de code

Dans une conversation de projet, le mode **Agent** (actif par défaut, comme dans Claude Code)
donne au modèle des outils sur le dossier du projet : `list_files`, `read_file` et
`search_files` (lecture, exécutés directement), puis `write_file`, `edit_file` et `run_command`
(modification, **soumis à votre accord**). Chaque appel s'affiche dans la réponse avec son
résultat repliable ; une action sensible attend un clic : « Allow once », « Always allow »
(pour toute la conversation) ou « Deny ». `run_command` n'a jamais « Always allow » : une
commande peut lire n'importe quel fichier, secrets compris, elle se valide donc une à une.

L'agent peut aussi **sortir de son projet**, mais jamais sans vous demander. Un chemin absolu
ou commençant par `~` (`~/Projects/heretic/README.md`) vise un autre dossier : la demande
affiche le dossier à ouvrir, le dépôt Git entier quand il y en a un, et propose « Allow once »,
« Open heretic for this conversation » ou « Deny ». Une fois ouvert, le dossier se lit comme le
projet ; y écrire demande toujours votre accord. Le dossier personnel entier ne s'ouvre jamais
pour la conversation, seulement pour un appel. Les **fichiers de secrets** se redemandent à
chaque fois, même dans un dossier ouvert : `.env`, clés privées (`id_ed25519`, `*.pem`…),
`~/.ssh`, `~/.config/cles`, `~/.aws`, `~/.claude`, `~/.kube`, `.npmrc`, historiques du shell,
et les fichiers qui feraient exécuter du code (`~/.bashrc`, `.git/hooks`, `.git/config`).
`list_files` et `search_files` ne les lisent jamais, `git_diff` les laisse de côté, et un commit
qui embarquerait un `.env` oublié par le `.gitignore` le signale, sans montrer son contenu.
Les dossiers ouverts sont oubliés au redémarrage de l'API.

Avant d'autoriser une écriture, on voit **exactement ce qui va changer** : un diff façon
`git diff`, lignes retirées en rouge, ajoutées en vert, numérotées, avec 3 lignes de contexte.
Il est calculé sans rien écrire (`difflib`), puis gardé dans l'historique : on peut revoir
plus tard ce que l'agent a modifié, fichier par fichier.

Un septième outil, `ask_user`, permet au modèle de **vous poser une question** quand une
décision vous revient : ses propositions s'affichent en boutons, et vous pouvez aussi taper
votre propre réponse.

Dans un dépôt Git, l'agent a aussi `git_status`, `git_diff` et `git_log` (lecture), et
`git_commit`, soumis à votre accord : la demande affiche le message et le diff de **chaque
fichier** qui sera enregistré, nouveaux fichiers compris. Les commits sont signés
« Netherbrain agent », pour que l'historique dise qui a fait quoi. Git est lancé sans shell, avec
une configuration neutre et **sans les hooks du dépôt** : un dépôt piégé ne peut pas exécuter de
code au moment d'un commit. Ni push, ni checkout, ni reset : l'agent enregistre, vous décidez
du reste.

Pour faire travailler l'agent sur un de vos dépôts sans toucher au vrai, clonez-le à côté,
sur une branche à lui, faites du clone un projet, puis récupérez son travail comme celui d'un
collègue :

```bash
git clone ~/Projects/mon-app ~/netherbrain-workspace/mon-app
git -C ~/netherbrain-workspace/mon-app switch -c agent
# plus tard, depuis le vrai dépôt :
git -C ~/Projects/mon-app pull ~/netherbrain-workspace/mon-app agent
```

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

## Modèles servis par llama.cpp

Ollama ne lit que les formats de GGUF présents dans llama.cpp officiel. Pour les autres (les
quantifications ternaires, par exemple), on lance soi-même `llama-server`, qui expose la même
API qu'OpenAI, et on donne son adresse à Netherbrain :

```bash
llama-server -m modele.gguf --mmproj mmproj.gguf --jinja -ngl 99 -fa on -c 32768 \
  --alias mon-modele --host 127.0.0.1 --port 8080
# puis, dans backend/.env (ou LLAMACPP_BASE_URL pour Docker) :
NETHERBRAIN_LLAMACPP_BASE_URL=http://localhost:8080/v1
```

Le fournisseur apparaît alors à côté d'Ollama, avec ses modèles. Comme `/v1/models` ne donne
presque rien, Netherbrain interroge `/props` : il y lit la fenêtre de contexte, la vision
(`modalities`) et l'appel d'outils, déduit du gabarit de discussion. Sans réponse de `/props`,
le modèle reste utilisable, simplement sans ces détails. `--jinja` est nécessaire pour que
llama.cpp accepte les outils, et `--mmproj` pour les images.

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
