"""Which models of a remote catalog are worth showing in a chat UI."""


def is_free_openrouter_model(model_id: str) -> bool:
    """OpenRouter marks its zero-cost variants with a ":free" suffix."""
    return model_id.endswith(":free")


# Groq also serves speech-to-text, text-to-speech and moderation models on the same endpoint.
_GROQ_NON_CHAT_MARKERS = ("whisper", "tts", "guard", "orpheus")


def is_groq_chat_model(model_id: str) -> bool:
    return not any(marker in model_id.lower() for marker in _GROQ_NON_CHAT_MARKERS)
