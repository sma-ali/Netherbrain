"""Quels modèles d'un catalogue distant méritent d'être affichés dans l'interface de chat."""


def is_free_openrouter_model(model_id: str) -> bool:
    """OpenRouter signale ses variantes gratuites par le suffixe « :free »."""
    return model_id.endswith(":free")


# Groq sert aussi des modèles de transcription, de synthèse vocale et de modération
# sur le même endpoint : on les écarte.
_GROQ_NON_CHAT_MARKERS = ("whisper", "tts", "guard", "orpheus")


def is_groq_chat_model(model_id: str) -> bool:
    return not any(marker in model_id.lower() for marker in _GROQ_NON_CHAT_MARKERS)
