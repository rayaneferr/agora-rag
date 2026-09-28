"""Providers LLM : vérification de la clé et liste des modèles utilisables pour le chat.

Premier jet : OpenAI seulement. Ajouter un provider = une entrée dans PROVIDERS + sa fonction list_models.
"""

import os
import re
from dataclasses import asdict, dataclass

from agora.agent import scrub


@dataclass
class Provider:
    id: str
    name: str
    key_url: str
    key_hint: str
    available: bool = True
    note: str = ""


PROVIDERS = [
    Provider(
        "openai",
        "OpenAI",
        "https://platform.openai.com/api-keys",
        "sk-…",
        note="Clé API de platform.openai.com (distincte d'un abonnement ChatGPT).",
    ),
    Provider("anthropic", "Anthropic", "https://console.anthropic.com/settings/keys", "sk-ant-…", available=False),
    Provider("gemini", "Google Gemini", "https://aistudio.google.com/apikey", "AIza…", available=False),
]
DEMO = Provider("demo", "Mode démo", "", "", note="Faux LLM sans clé, pour tester l'interface.")


def demo_enabled() -> bool:
    return os.getenv("AGORA_DEMO") == "1"


def list_providers() -> list[dict]:
    return [asdict(p) for p in PROVIDERS + ([DEMO] if demo_enabled() else [])]


# Modèles OpenAI qui ne servent pas au chat avec outils (audio, images, embeddings, recherche…).
_OPENAI_CHAT = re.compile(r"^(gpt-|o\d|chatgpt-)")
_OPENAI_EXCLUDE = re.compile(r"audio|realtime|tts|transcribe|image|search|embedding|moderation|instruct|codex|dall-e")
# Choix par défaut : bon rapport qualité/coût pour du RAG ; sinon le plus récent de la liste.
_OPENAI_PREFERRED = ["gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini"]


class ProviderError(Exception):
    """Clé invalide ou provider injoignable, avec un message présentable."""


async def list_models(provider: str, api_key: str) -> dict:
    if provider == "demo" and demo_enabled():
        return {"models": [{"id": "demo/scripted", "label": "LLM scripté (démo)"}], "default": "demo/scripted"}
    if provider != "openai":
        raise ProviderError(f"Provider « {provider} » pas encore disponible.")

    import openai

    try:
        page = await openai.AsyncOpenAI(api_key=api_key, max_retries=1, timeout=15).models.list()
    except openai.AuthenticationError as exc:
        raise ProviderError(
            "Clé refusée par OpenAI. Vérifie qu'il s'agit bien d'une clé API (platform.openai.com)."
        ) from exc
    except openai.APIConnectionError as exc:
        raise ProviderError("Impossible de joindre OpenAI (réseau ?).") from exc
    except openai.APIError as exc:
        raise ProviderError(f"Erreur OpenAI : {scrub(str(exc), api_key)[:300]}") from exc

    models = sorted(
        (m for m in page.data if _OPENAI_CHAT.match(m.id) and not _OPENAI_EXCLUDE.search(m.id)),
        key=lambda m: -m.created,
    )
    ids = [m.id for m in models]
    default = next((m for m in _OPENAI_PREFERRED if m in ids), ids[0] if ids else None)
    # LiteLLM attend « provider/modèle ».
    return {"models": [{"id": f"openai/{i}", "label": i} for i in ids], "default": default and f"openai/{default}"}
