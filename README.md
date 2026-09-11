# Netherbrain

> Many minds, one interface.

Netherbrain is a self-hostable chat platform that orchestrates several open-source LLMs:
local models running on your own GPU through [Ollama](https://ollama.com), and remote models
through any OpenAI-compatible API.

## Status

Early development. Current milestone: **streaming chat backend**.

- [x] FastAPI gateway streaming answers from Ollama (Server-Sent Events)
- [x] Reasoning ("thinking") tokens streamed separately from the answer
- [x] Per-answer metrics: time to first token, tokens per second
- [ ] Next.js chat interface
- [ ] Multiple providers (OpenRouter, Groq...) with graceful degradation when offline
- [ ] Persistent conversations (PostgreSQL) and authentication
- [ ] Docker Compose, CI
- [ ] Side-by-side model comparison
- [ ] RAG over your own documents

## Architecture

```
Browser ──HTTP/SSE──> FastAPI gateway ──OpenAI-compatible API──> Ollama (local GPU)
                                                            └──> remote providers (soon)
```

The API layer depends only on an `LLMProvider` interface; every backend speaking the
OpenAI Chat Completions API is handled by a single `OpenAICompatibleProvider` class.

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and a running [Ollama](https://ollama.com) with
at least one model (`ollama pull qwen3:8b`).

```bash
cd backend
uv sync                      # create the virtualenv and install dependencies
uv run uvicorn netherbrain.main:app --reload
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

## API

| Method | Path          | Description                                  |
|--------|---------------|----------------------------------------------|
| GET    | `/api/health` | Liveness probe                               |
| GET    | `/api/models` | Models available from the provider           |
| POST   | `/api/chat`   | Streams an answer as Server-Sent Events      |

`/api/chat` emits `reasoning` and `token` events, then a final `done` event carrying metrics
(`ttft_ms`, `total_ms`, `tokens_per_second`...) or an `error` event.
