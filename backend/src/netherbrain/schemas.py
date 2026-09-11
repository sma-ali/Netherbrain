"""Data contracts shared by the API layer and the providers."""

from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)


class ModelInfo(BaseModel):
    id: str
    provider: str


# --- Events yielded by a provider while it streams an answer ---


class TokenEvent(BaseModel):
    """A piece of the final answer."""

    type: Literal["token"] = "token"
    content: str


class ReasoningEvent(BaseModel):
    """A piece of the model's "thinking" (reasoning models such as Qwen3 or DeepSeek-R1)."""

    type: Literal["reasoning"] = "reasoning"
    content: str


class UsageEvent(BaseModel):
    """Token accounting, sent once at the end of the stream."""

    type: Literal["usage"] = "usage"
    prompt_tokens: int
    completion_tokens: int


StreamEvent = TokenEvent | ReasoningEvent | UsageEvent
