# Netherbrain

> Many minds, one interface.

Netherbrain is a self-hostable chat platform that orchestrates several open-source LLMs:
local models running on your own GPU through [Ollama](https://ollama.com), and remote models
through any OpenAI-compatible API.

## Status

Early development. Current milestone: **streaming chat, end to end**.

- [x] FastAPI gateway streaming answers from Ollama (Server-Sent Events)
- [x] Reasoning ("thinking") tokens streamed separately from the answer
- [x] Per-answer metrics: time to first token, tokens per second
- [x] Next.js chat interface: model picker, Markdown answers, collapsible reasoning, stop button
- [ ] Multiple providers (OpenRouter, Groq...) with graceful degradation when offline
- [ ] Persistent conversations (PostgreSQL) and authentication
- [ ] Docker Compose, CI
- [ ] Side-by-side model comparison
- [ ] RAG over your own documents

## Architecture

```
Next.js UI ──HTTP/SSE──> FastAPI gateway ──OpenAI-compatible API──> Ollama (local GPU)
 (browser)                                                     └──> remote providers (soon)
```

| Folder      | Stack                                                                 |
|-------------|-----------------------------------------------------------------------|
| `backend/`  | Python 3.14, FastAPI, Pydantic, OpenAI SDK, uv, pytest, Ruff          |
| `frontend/` | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Vitest |

The API layer depends only on an `LLMProvider` interface; every backend speaking the
OpenAI Chat Completions API is handled by a single `OpenAICompatibleProvider` class.
The browser reads the SSE stream from a `fetch` response with a small incremental parser
(`EventSource` only supports GET).

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/), Node.js 24+ and a running
[Ollama](https://ollama.com) with at least one model (`ollama pull qwen3:8b`).

```bash
# Terminal 1: API on http://localhost:8000
cd backend
uv sync                      # create the virtualenv and install dependencies
uv run uvicorn netherbrain.main:app --reload
```

```bash
# Terminal 2: UI on http://localhost:3000
cd frontend
npm install
npm run dev
```

Interactive API docs: <http://localhost:8000/docs>

```bash
curl -N localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"model": "qwen3:8b", "messages": [{"role": "user", "content": "Hello!"}]}'
```

### Development

```bash
cd backend
uv run pytest                # tests (no GPU or network needed: providers are faked)
uv run ruff check .          # lint
uv run ruff format .         # format
```

```bash
cd frontend
npm test                     # unit tests (Vitest)
npm run lint                 # ESLint
npm run build                # production build + type checking
```

## API

| Method | Path          | Description                                  |
|--------|---------------|----------------------------------------------|
| GET    | `/api/health` | Liveness probe                               |
| GET    | `/api/models` | Models available from the provider           |
| POST   | `/api/chat`   | Streams an answer as Server-Sent Events      |

`/api/chat` emits `reasoning` and `token` events, then a final `done` event carrying metrics
(`ttft_ms`, `total_ms`, `tokens_per_second`...) or an `error` event.
