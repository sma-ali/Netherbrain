"""Le cœur du streaming : relayer les événements d'un fournisseur en Server-Sent Events."""

import json
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from fastapi.responses import StreamingResponse

from netherbrain.agent.approvals import ApprovalRegistry, Reply
from netherbrain.agent.tools import ASK_USER, Toolbox, ToolResult
from netherbrain.providers import LLMProvider, ProviderError
from netherbrain.schemas import ChatMessage, TokenEvent, ToolCallEvent, UsageEvent


@dataclass
class StreamResult:
    """Ce qui a été généré, accumulé au fil du stream pour pouvoir l'enregistrer ensuite."""

    content: str = ""
    reasoning: str = ""
    metrics: dict[str, Any] | None = None
    error: str | None = None
    finished: bool = False
    # Les appels d'outils de l'agent, dans l'ordre (liste vide hors mode agent).
    steps: list[dict[str, Any]] = field(default_factory=list)


def sse(event: str, data: dict[str, Any]) -> str:
    """Formate un Server-Sent Event : une ligne `event:`, une ligne `data:`, une ligne vide."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_response(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        # Désactive les caches et les tampons des proxys : chaque événement part aussitôt.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def stream_answer(
    provider: LLMProvider, model: str, messages: list[ChatMessage], result: StreamResult
) -> AsyncIterator[str]:
    """Streame la réponse du modèle sous forme de Server-Sent Events.

    Types d'événements : `reasoning`, `token`, puis `done` (avec les métriques)
    ou `error`. Au passage, `result` accumule ce qui a été généré.
    """
    started = time.perf_counter()
    first_token_at: float | None = None
    usage: UsageEvent | None = None

    try:
        async for event in provider.stream_chat(model, messages):
            if isinstance(event, UsageEvent):
                usage = event
                continue
            if isinstance(event, ToolCallEvent):
                continue  # sans outils fournis, le modèle ne devrait pas en demander
            if first_token_at is None:
                first_token_at = time.perf_counter()
            if isinstance(event, TokenEvent):
                result.content += event.content
            else:
                result.reasoning += event.content
            yield sse(event.type, event.model_dump(exclude={"type"}))
    except ProviderError as exc:
        # Une fois le stream commencé, le statut 200 est déjà parti :
        # les erreurs doivent donc voyager à l'intérieur du stream.
        result.error = str(exc)
        yield sse("error", {"message": result.error})
        return

    result.metrics = compute_metrics(started, first_token_at, time.perf_counter(), usage)
    result.finished = True
    yield sse("done", result.metrics)


async def stream_agent(
    provider: LLMProvider,
    model: str,
    messages: list[ChatMessage],
    result: StreamResult,
    *,
    toolbox: Toolbox,
    approvals: ApprovalRegistry,
    conversation_id: uuid.UUID,
    max_steps: int,
) -> AsyncIterator[str]:
    """La boucle de l'agent : le modèle demande des outils, on les exécute, il recommence.

    Elle s'arrête quand le modèle répond sans demander d'outil, ou au bout de `max_steps`
    tours. Trois événements s'ajoutent à ceux de `stream_answer` : `tool_call` (le modèle
    demande un outil), `tool_request` (il faut l'accord de l'utilisateur) et `tool_result`.
    """
    history = list(messages)
    started = time.perf_counter()
    first_token_at: float | None = None
    usage: UsageEvent | None = None

    for _ in range(max_steps):
        calls: list[ToolCallEvent] = []
        answered = ""
        try:
            async for event in provider.stream_chat(model, history, tools=toolbox.schemas):
                if isinstance(event, UsageEvent):
                    usage = _total_usage(usage, event)
                    continue
                if isinstance(event, ToolCallEvent):
                    calls.append(event)
                    continue
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                if isinstance(event, TokenEvent):
                    result.content += event.content
                    answered += event.content
                else:
                    result.reasoning += event.content
                yield sse(event.type, event.model_dump(exclude={"type"}))
        except ProviderError as exc:
            result.error = str(exc)
            yield sse("error", {"message": result.error})
            return

        if not calls:
            break  # le modèle a répondu sans rien demander : c'est fini

        # Le modèle doit retrouver ses propres demandes dans l'historique du tour suivant.
        history.append(
            ChatMessage(
                role="assistant",
                content=answered,
                tool_calls=[
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": call.arguments},
                    }
                    for call in calls
                ],
            )
        )
        for call in calls:
            async for chunk in _run_call(
                call, toolbox, approvals, conversation_id, result, history
            ):
                yield chunk
    else:
        # La boucle est allée au bout sans que le modèle conclue : on coupe court.
        result.error = f"Stopped after {max_steps} tool calls."
        yield sse("error", {"message": result.error})
        return

    result.metrics = compute_metrics(started, first_token_at, time.perf_counter(), usage)
    result.metrics["tool_calls"] = len(result.steps)
    result.finished = True
    yield sse("done", result.metrics)


async def _run_call(
    call: ToolCallEvent,
    toolbox: Toolbox,
    approvals: ApprovalRegistry,
    conversation_id: uuid.UUID,
    result: StreamResult,
    history: list[ChatMessage],
) -> AsyncIterator[str]:
    """Un appel d'outil : autorisation ou question éventuelle, exécution, trace pour le modèle.

    Quand il faut l'utilisateur, le stream s'arrête sur `approvals.wait` : sa réponse arrive
    par une autre requête HTTP (un SSE ne va que du serveur vers le navigateur).
    """
    arguments = _arguments(call.arguments)
    summary = toolbox.describe(call.name, arguments or {})
    yield sse("tool_call", {"id": call.id, "name": call.name, "summary": summary})

    if arguments is None:
        outcome, state = ToolResult("Arguments are not valid JSON.", error=True), "error"
    elif call.name == ASK_USER:
        options = [str(option) for option in arguments.get("options") or []][:4]
        yield sse(
            "tool_request",
            {
                "id": call.id,
                "name": call.name,
                "summary": summary,
                "kind": "question",
                "question": str(arguments.get("question", "")),
                "options": options,
            },
        )
        reply = await approvals.wait(conversation_id, call.id, call.name)
        if reply is None or reply.decision != "answer":
            outcome, state = ToolResult("The user did not answer.", error=True), "error"
        else:
            outcome, state = ToolResult(f"The user answered: {reply.answer}"), "done"
    else:
        reply = Reply("once")
        if toolbox.needs_approval(call.name) and not approvals.allowed(conversation_id, call.name):
            yield sse(
                "tool_request",
                {
                    "id": call.id,
                    "name": call.name,
                    "summary": summary,
                    "kind": "approval",
                    "arguments": arguments,
                },
            )
            # Sans réponse à temps, c'est un refus.
            reply = await approvals.wait(conversation_id, call.id, call.name) or Reply("deny")
        if reply.decision not in ("once", "always"):
            outcome, state = ToolResult("The user refused this action.", error=True), "denied"
        else:
            outcome = await toolbox.run(call.name, arguments)
            state = "error" if outcome.error else "done"

    step = {
        "id": call.id,
        "name": call.name,
        "summary": summary,
        "status": state,
        "output": outcome.output,
    }
    result.steps.append(step)
    yield sse("tool_result", step)
    # Le résultat repart vers le modèle sous forme de message « tool ».
    history.append(ChatMessage(role="tool", tool_call_id=call.id, content=outcome.output))


def _arguments(raw: str) -> dict[str, Any] | None:
    """Les arguments écrits par le modèle ; None s'il n'a pas produit un objet JSON."""
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _total_usage(previous: UsageEvent | None, event: UsageEvent) -> UsageEvent:
    """Les jetons s'additionnent sur tous les tours de la boucle."""
    if previous is None:
        return event
    return UsageEvent(
        prompt_tokens=previous.prompt_tokens + event.prompt_tokens,
        completion_tokens=previous.completion_tokens + event.completion_tokens,
    )


def compute_metrics(
    started: float, first_token_at: float | None, finished: float, usage: UsageEvent | None
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "total_ms": round((finished - started) * 1000),
        "ttft_ms": round((first_token_at - started) * 1000) if first_token_at else None,
    }
    if usage:
        generation_s = finished - (first_token_at or started)
        metrics["prompt_tokens"] = usage.prompt_tokens
        metrics["completion_tokens"] = usage.completion_tokens
        metrics["tokens_per_second"] = (
            round(usage.completion_tokens / generation_s, 1) if generation_s > 0 else None
        )
    return metrics
