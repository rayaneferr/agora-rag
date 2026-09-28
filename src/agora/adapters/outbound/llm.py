"""Adaptateurs sortants « LLM » : Ollama (modèles locaux, API native) et un LLM scripté de démonstration.

Chacun implémente LLMPort. Agora tourne entièrement en local : pas de clé API, rien ne sort de la machine.
Ollama est appelé directement en HTTP (`/api/chat`, streaming NDJSON) : pas de SDK intermédiaire.
"""

import asyncio
import contextlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass

import httpx

from agora.core.agent import LLMError

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# La fenêtre par défaut d'Ollama (2 à 4k tokens) tronque en silence les extraits renvoyés par les outils.
OLLAMA_NUM_CTX = 16384
# Un modèle de 14B peut mettre une minute à se charger avant le premier token : on attend, sans limite courte.
OLLAMA_TIMEOUT = httpx.Timeout(10.0, read=600.0)
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


def to_ollama_messages(messages: list[dict]) -> list[dict]:
    """Format interne (OpenAI : arguments en JSON texte) → format Ollama (arguments en objet)."""
    out = []
    for m in messages:
        msg = {"role": m["role"], "content": m.get("content") or ""}
        if calls := m.get("tool_calls"):
            msg["tool_calls"] = [
                {"function": {"name": c["function"]["name"], "arguments": _as_dict(c["function"].get("arguments"))}}
                for c in calls
            ]
        out.append(msg)
    return out


def _as_dict(arguments) -> dict:
    if isinstance(arguments, dict):
        return arguments
    with contextlib.suppress(json.JSONDecodeError, TypeError):
        parsed = json.loads(arguments or "{}")
        if isinstance(parsed, dict):
            return parsed
    return {}


def from_ollama_tool_calls(calls: list[dict]) -> list[dict]:
    """Format Ollama → format interne, avec un id par appel (Ollama n'en fournit pas toujours)."""
    return [
        {
            "id": c.get("id") or f"call_{uuid.uuid4().hex[:12]}",
            "type": "function",
            "function": {
                "name": c["function"]["name"],
                "arguments": json.dumps(c["function"].get("arguments") or {}, ensure_ascii=False),
            },
        }
        for c in calls
    ]


def _classify(exc: Exception, model: str) -> LLMError:
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return LLMError("network", f"Impossible de joindre Ollama sur {OLLAMA_URL}. L'application est-elle lancée ?")
    if isinstance(exc, httpx.ReadTimeout):
        return LLMError("timeout", "Le modèle n'a pas répondu à temps.")
    if isinstance(exc, httpx.HTTPStatusError):
        detail = ""
        with contextlib.suppress(Exception):
            detail = exc.response.json().get("error", "")
        if exc.response.status_code == 404:
            text = f"Modèle introuvable dans Ollama : `ollama pull {model}`."
            return LLMError("model", f"{text}\n\nDétail : {detail[:300]}")
        if exc.response.status_code == 400:
            return LLMError("bad_request", f"Requête refusée par Ollama.\n\nDétail : {detail[:300]}")
        return LLMError("unknown", f"Ollama a répondu {exc.response.status_code}.\n\nDétail : {detail[:300]}")
    return LLMError("unknown", f"Erreur inattendue : {str(exc)[:300]}")


def ollama(model: str):
    """LLMPort branché sur un modèle Ollama local (API native, streaming NDJSON)."""

    async def stream(messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
        body = {
            "model": model,
            "messages": to_ollama_messages(messages),
            "tools": tools,
            "stream": True,
            "options": {"num_ctx": OLLAMA_NUM_CTX},
        }
        content, calls, usage = [], [], None
        try:
            async with (
                httpx.AsyncClient(base_url=OLLAMA_URL, timeout=OLLAMA_TIMEOUT) as client,
                client.stream("POST", "/api/chat", json=body) as response,
            ):
                if response.status_code >= 400:
                    await response.aread()
                    response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise LLMError("unknown", f"Ollama : {chunk['error'][:300]}")
                    msg = chunk.get("message") or {}
                    if token := msg.get("content"):
                        content.append(token)
                        yield {"token": token}
                    calls.extend(msg.get("tool_calls") or [])
                    if chunk.get("done"):
                        usage = {
                            "prompt_tokens": chunk.get("prompt_eval_count") or 0,
                            "completion_tokens": chunk.get("eval_count") or 0,
                        }
        except LLMError:
            raise
        except Exception as exc:
            raise _classify(exc, model) from exc
        message = {"role": "assistant", "content": "".join(content)}
        if calls:
            message["tool_calls"] = from_ollama_tool_calls(calls)
        yield {"final": recover_tool_calls(message, tools), "usage": usage}

    return stream


def demo():
    """LLMPort scripté : appelle vraiment le premier outil de recherche du contexte, puis résume.

    Sert à tester l'interface de bout en bout ; il ne « comprend » rien.
    """

    async def stream(messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
        last = messages[-1]
        name = next((t["function"]["name"] for t in tools if t["function"]["name"].startswith("search")), None)
        if last["role"] == "user" and name:
            args = json.dumps({"query": last["content"], "limit": 4}, ensure_ascii=False)
            call = {"id": "demo-1", "type": "function", "function": {"name": name, "arguments": args}}
            yield {"final": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": None}
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
        yield {"final": {"role": "assistant", "content": text}, "usage": None}

    return stream


def make_llm(provider: str, model: str):
    if provider == "demo" and demo_enabled():
        return demo()
    if provider == "ollama":
        return ollama(model)
    raise ProviderError(f"Fournisseur « {provider} » inconnu.")
