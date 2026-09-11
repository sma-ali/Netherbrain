# syntax=docker/dockerfile:1

# --- Étape de build : installer les dépendances avec uv ---
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /bin/uv

# Précompiler les .pyc (démarrage plus rapide), copier les fichiers depuis le cache au lieu de
# créer des liens physiques, et utiliser le Python de l'image au lieu d'en télécharger un.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Les dépendances d'abord : cette couche reste en cache tant que pyproject.toml et uv.lock
# ne changent pas, donc modifier le code ne réinstalle pas tous les paquets.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Puis l'application elle-même, installée comme un paquet classique (non éditable).
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Étape d'exécution : juste Python et l'environnement virtuel, sans uv ni sources ---
FROM python:3.14-slim

# Ne jamais tourner en root dans le conteneur.
RUN useradd --create-home --uid 1000 netherbrain
WORKDIR /app
COPY --from=builder --chown=netherbrain:netherbrain /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER netherbrain
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]

CMD ["uvicorn", "netherbrain.main:app", "--host", "0.0.0.0", "--port", "8000"]
