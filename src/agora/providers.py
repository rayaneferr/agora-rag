"""Providers LLM : vérification de la clé et liste des modèles utilisables pour le chat.

Disponibles : Ollama (modèles locaux, sans clé) et OpenAI. Ajouter un provider = une entrée dans
PROVIDERS + sa branche dans list_models.
"""

import asyncio
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
    needs_key: bool = True


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

PROVIDERS = [
    Provider(
        "ollama",
        "Ollama (local)",
        "https://ollama.com/download",
        "",
        note="Modèle qui tourne sur ta machine : gratuit, rien ne sort de l'ordinateur. Plus lent qu'une API.",
        needs_key=False,
    ),
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
DEMO = Provider("demo", "Mode démo", "", "", note="Faux LLM sans clé, pour tester l'interface.", needs_key=False)


def demo_enabled() -> bool:
    return os.getenv("AGORA_DEMO") == "1"


def list_providers() -> list[dict]:
    return [asdict(p) for p in PROVIDERS + ([DEMO] if demo_enabled() else [])]


# Modèles OpenAI qui ne servent pas au chat avec outils (audio, images, embeddings, recherche…).
_OPENAI_CHAT = re.compile(r"^(gpt-|o\d|chatgpt-)")
_OPENAI_EXCLUDE = re.compile(r"audio|realtime|tts|transcribe|image|search|embedding|moderation|instruct|codex|dall-e")
# Choix par défaut : bon rapport qualité/coût pour du RAG ; sinon le plus récent de la liste.
_OPENAI_PREFERRED = ["gpt-5.4-mini", "gpt-5-mini", "gpt-4.1-mini", "gpt-4o-mini"]


# Modèles locaux les plus fiables en appel d'outils (MCP) et en français, par ordre de préférence.
_OLLAMA_PREFERRED = ["qwen2.5:14b", "qwen3.5:35b", "qwen2.5:7b", "llama3.1:8b", "mistral-nemo:latest"]


class ProviderError(Exception):
    """Clé invalide ou provider injoignable, avec un message présentable."""


async def _ollama_models() -> dict:
    import httpx

    try:
        async with httpx.AsyncClient(base_url=OLLAMA_URL, timeout=10) as client:
            tags = (await client.get("/api/tags")).json()["models"]
            shows = await asyncio.gather(*(client.post("/api/show", json={"model": m["name"]}) for m in tags))
    except httpx.HTTPError as exc:
        raise ProviderError(
            f"Ollama ne répond pas sur {OLLAMA_URL}. Lance l'application Ollama (ou `ollama serve`)."
        ) from exc
    # Sans appel d'outils, le modèle ne peut pas interroger les serveurs MCP : on l'écarte.
    usable = [
        (m["name"], m["details"].get("parameter_size", "?"))
        for m, show in zip(tags, shows, strict=True)
        if "tools" in show.json().get("capabilities", [])
    ]
    if not usable:
        raise ProviderError("Aucun modèle Ollama avec appel d'outils. Essaie : `ollama pull qwen2.5:14b`.")
    names = [n for n, _ in usable]
    default = next((m for m in _OLLAMA_PREFERRED if m in names), names[0])
    return {
        "models": [{"id": f"ollama_chat/{n}", "label": f"{n} · {size}"} for n, size in usable],
        "default": f"ollama_chat/{default}",
    }


async def list_models(provider: str, api_key: str) -> dict:
    if provider == "demo" and demo_enabled():
        return {"models": [{"id": "demo/scripted", "label": "LLM scripté (démo)"}], "default": "demo/scripted"}
    if provider == "ollama":
        return await _ollama_models()
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
