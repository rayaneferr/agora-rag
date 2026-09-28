"""Adaptateurs sortants « LLM » : Ollama (modèles locaux, via LiteLLM) et un LLM scripté de démonstration.

Chacun implémente LLMPort. Agora tourne entièrement en local : pas de clé API, rien ne sort de la machine.
"""

import asyncio
import contextlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass

import litellm

from agora.core.agent import LLMError, scrub

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# La fenêtre par défaut d'Ollama (2 à 4k tokens) tronque en silence les extraits renvoyés par les outils.
OLLAMA_NUM_CTX = 16384
# Modèles locaux les plus fiables en appel d'outils (MCP) et en français, par ordre de préférence.
PREFERRED = ["qwen2.5:14b", "qwen3.5:35b", "qwen2.5:7b", "llama3.1:8b", "mistral-nemo:latest"]


@dataclass
class Provider:
    id: str
    name: str
    note: str
    install_url: str = ""


OLLAMA = Provider(
    "ollama",
    "Ollama",
    "Le modèle tourne sur ta machine : gratuit, hors ligne, rien ne sort de l'ordinateur.",
    "https://ollama.com/download",
)
DEMO = Provider("demo", "Mode démo", "Faux LLM instantané, pour découvrir l'interface.")


class ProviderError(Exception):
    """Fournisseur injoignable ou inutilisable, avec un message présentable."""


def demo_enabled() -> bool:
    return os.getenv("AGORA_DEMO") == "1"


def list_providers() -> list[dict]:
    return [asdict(p) for p in [OLLAMA] + ([DEMO] if demo_enabled() else [])]


async def list_models(provider: str) -> dict:
    if provider == "demo" and demo_enabled():
        return {"models": [{"id": "demo", "label": "LLM scripté", "size": ""}], "default": "demo"}
    if provider != "ollama":
        raise ProviderError(f"Fournisseur « {provider} » inconnu.")

    import httpx

    try:
        async with httpx.AsyncClient(base_url=OLLAMA_URL, timeout=10) as client:
            tags = (await client.get("/api/tags")).json()["models"]
            shows = await asyncio.gather(*(client.post("/api/show", json={"model": m["name"]}) for m in tags))
    except httpx.HTTPError as exc:
        raise ProviderError(f"Ollama ne répond pas sur {OLLAMA_URL}. Lance l'application Ollama.") from exc
    # Sans appel d'outils, le modèle ne peut pas interroger les serveurs MCP : on l'écarte.
    usable = [
        {"id": m["name"], "label": m["name"], "size": m["details"].get("parameter_size", "")}
        for m, show in zip(tags, shows, strict=True)
        if "tools" in show.json().get("capabilities", [])
    ]
    if not usable:
        raise ProviderError("Aucun modèle Ollama ne sait appeler des outils. Essaie : ollama pull qwen2.5:14b")
    names = [m["id"] for m in usable]
    return {"models": usable, "default": next((m for m in PREFERRED if m in names), names[0])}


def _classify(exc: Exception) -> LLMError:
    message = scrub(str(exc))
    kinds = [
        (litellm.APIConnectionError, "network", "Impossible de joindre Ollama. L'application est-elle lancée ?"),
        (litellm.NotFoundError, "model", "Modèle introuvable dans Ollama."),
        (litellm.ContextWindowExceededError, "context", "Conversation trop longue pour ce modèle."),
        (litellm.BadRequestError, "bad_request", "Requête refusée par le modèle."),
    ]
    for cls, kind, text in kinds:
        if isinstance(exc, cls):
            return LLMError(kind, f"{text}\n\nDétail : {message[:400]}")
    return LLMError("unknown", f"Erreur inattendue : {message[:400]}")


def recover_tool_calls(message: dict, tools: list[dict]) -> dict:
    """Récupère un appel d'outil que le modèle a écrit en texte au lieu de le structurer.

    Les modèles locaux (qwen2.5 notamment) renvoient parfois `{"name": …, "arguments": …}</tool_call>` dans le
    contenu : Ollama ne le reconnaît pas, et la « réponse » affichée serait du JSON. On ne convertit que les
    objets qui nomment un outil réellement exposé ; tout autre texte reste une réponse.
    """
    content = message.get("content") or ""
    if message.get("tool_calls") or '"name"' not in content:
        return message
    known = {t["function"]["name"] for t in tools}
    decoder, calls, i = json.JSONDecoder(), [], 0
    while (i := content.find("{", i)) >= 0:
        try:
            obj, end = decoder.raw_decode(content, i)
        except json.JSONDecodeError:
            i += 1
            continue
        i = end
        if isinstance(obj, dict) and obj.get("name") in known:
            args = obj.get("arguments", obj.get("parameters", {}))
            calls.append(
                {
                    "id": f"call_{uuid.uuid4().hex[:12]}",
                    "type": "function",
                    "function": {"name": obj["name"], "arguments": args if isinstance(args, str) else json.dumps(args)},
                }
            )
    if not calls:
        return message
    return {**message, "content": "", "tool_calls": calls}


def ollama(model: str):
    """LLMPort branché sur un modèle Ollama local."""

    async def stream(messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
        try:
            response = await litellm.acompletion(
                model=f"ollama_chat/{model}",
                api_base=OLLAMA_URL,
                messages=messages,
                tools=tools,
                stream=True,
                num_ctx=OLLAMA_NUM_CTX,
            )
            chunks = []
            async for chunk in response:
                chunks.append(chunk)
                if chunk.choices and (delta := chunk.choices[0].delta) and delta.content:
                    yield {"token": delta.content}
        except Exception as exc:
            raise _classify(exc) from exc
        full = litellm.stream_chunk_builder(chunks, messages=messages)
        usage = full.usage and {
            "prompt_tokens": full.usage.prompt_tokens,
            "completion_tokens": full.usage.completion_tokens,
        }
        message = recover_tool_calls(full.choices[0].message.model_dump(exclude_none=True), tools)
        yield {"final": message, "usage": usage, "cost": 0.0}

    return stream


def demo():
    """LLMPort scripté : appelle vraiment le premier outil de recherche du contexte, puis résume.

    Sert à tester l'interface de bout en bout ; il ne « comprend » rien.
    """

    async def stream(messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
        last = messages[-1]
        if last["role"] == "user":
            name = next((t["function"]["name"] for t in tools if t["function"]["name"].startswith("search")), None)
            args = json.dumps({"query": last["content"], "limit": 4}, ensure_ascii=False)
            call = {"id": "demo-1", "type": "function", "function": {"name": name, "arguments": args}}
            yield {"final": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": None, "cost": 0.0}
            return
        results = []
        with contextlib.suppress(json.JSONDecodeError):
            results = json.loads(last["content"])
        lines = ["*Mode démo : pas de vrai modèle, je liste ce que les outils ont trouvé.*", ""]
        for r in results if isinstance(results, list) else []:
            if "title" in r:
                lines.append(f"- **{r['title']}** ({r.get('year')}) — {(r.get('summary') or '')[:220]}")
            else:
                lines.append(f"- **{r.get('orateur')}**, {r.get('date')} — {r.get('sujet') or r.get('section')}")
        text = "\n".join(lines) if len(lines) > 2 else "Les outils n'ont rien trouvé."
        for i in range(0, len(text), 12):
            yield {"token": text[i : i + 12]}
            await asyncio.sleep(0.01)
        yield {"final": {"role": "assistant", "content": text}, "usage": None, "cost": 0.0}

    return stream


def make_llm(provider: str, model: str):
    if provider == "demo" and demo_enabled():
        return demo()
    if provider == "ollama":
        return ollama(model)
    raise ProviderError(f"Fournisseur « {provider} » inconnu.")
