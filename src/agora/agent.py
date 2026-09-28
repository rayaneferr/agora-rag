"""Boucle agent partagée par la CLI et l'API web.

Le LLM (via LiteLLM, clé de l'utilisateur) appelle les outils des serveurs MCP jusqu'à pouvoir
répondre. Tout ce qui se passe est émis sous forme d'événements, pour que l'interface montre
en direct ce que fait l'assistant : réflexion, appels d'outils, sources, texte, coût.
"""

import contextlib
import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import litellm

from agora.common import ROOT

MAX_TOOL_ROUNDS = 8
# Fenêtre de contexte des modèles Ollama : la valeur par défaut (2 à 4k tokens) tronque en silence
# les extraits renvoyés par les outils. 16k couvre plusieurs recherches dans un même tour.
OLLAMA_NUM_CTX = 16384

SYSTEM_PROMPT = """Tu es Agora, un assistant spécialisé en cinéma et en vie parlementaire française.
Tu disposes d'outils de recherche sur deux bases : des synopsis de films (Wikipedia, en anglais) et les
comptes rendus des séances de l'Assemblée nationale (17e législature, depuis juillet 2024).

- Appuie-toi sur ces outils plutôt que sur ta mémoire. Si les résultats sont décevants, reformule
  (par exemple en anglais pour les films) ou relance une recherche avec d'autres filtres.
- Pour une question sur une personne, trouve d'abord son nom exact avec find_orateurs.
- N'ajoute pas de filtre (dates, genre, réalisateur…) que l'utilisateur n'a pas demandé. Si une recherche
  filtrée ne renvoie rien, relance-la avec moins de filtres avant de conclure.
- Cite tes sources : titre et année pour un film ; orateur, date et lien de la séance pour un débat.
- Si les outils ne trouvent rien, dis-le au lieu d'inventer.
- Réponds en français, de façon claire et structurée (Markdown)."""


@dataclass
class Turn:
    """Ce qu'il faut pour répondre à un message : modèle, clé, historique."""

    model: str
    api_key: str | None
    api_base: str | None = None  # ex. serveur Ollama
    history: list[dict] = field(default_factory=list)  # [{"role": "user"|"assistant", "content": str}]
    message: str = ""


class LLMError(Exception):
    """Erreur côté provider, avec un message présentable à l'utilisateur."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def scrub(text: str, secret: str | None) -> str:
    """Une clé ne doit jamais ressortir dans un message d'erreur ou un log."""
    if secret:
        text = text.replace(secret, "sk-***")
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", text)


def classify_error(exc: Exception, api_key: str | None) -> LLMError:
    message = scrub(str(exc), api_key)
    kinds = [
        (litellm.AuthenticationError, "auth", "Clé API refusée par le provider. Vérifie-la dans les réglages."),
        (litellm.RateLimitError, "rate_limit", "Limite atteinte chez le provider (quota ou crédits épuisés ?)."),
        (litellm.NotFoundError, "model", "Modèle introuvable ou non disponible pour cette clé."),
        (litellm.ContextWindowExceededError, "context", "Conversation trop longue pour ce modèle."),
        (litellm.BadRequestError, "bad_request", "Requête refusée par le provider."),
        (litellm.APIConnectionError, "network", "Impossible de joindre le provider (réseau ?)."),
    ]
    for cls, kind, text in kinds:
        if isinstance(exc, cls):
            return LLMError(kind, f"{text}\n\nDétail : {message[:400]}")
    return LLMError("unknown", f"Erreur inattendue : {message[:400]}")


# --- Sources : ce que l'interface affiche comme références cliquables -----------------------


def extract_sources(tool: str, payload: Any) -> list[dict]:
    items = payload if isinstance(payload, list) else [payload]
    sources = []
    for it in items:
        if not isinstance(it, dict) or "error" in it:
            continue
        if tool in ("search_films", "get_film"):
            sources.append(
                {
                    "kind": "film",
                    "title": it.get("title"),
                    "subtitle": " · ".join(str(x) for x in (it.get("year"), it.get("director")) if x),
                    "url": it.get("wiki_url"),
                    "excerpt": (it.get("summary") or it.get("matching_excerpt") or it.get("plot") or "")[:280],
                    "score": it.get("score"),
                }
            )
        elif tool in ("search_debats", "get_contexte"):
            who = it.get("orateur", "")
            if it.get("groupe"):
                who += f" ({it['groupe']})"
            sources.append(
                {
                    "kind": "debat",
                    "title": who,
                    "subtitle": " · ".join(x for x in (it.get("date"), it.get("section"), it.get("sujet")) if x),
                    "url": it.get("url"),
                    "excerpt": (it.get("texte") or "")[:280],
                    "score": it.get("score"),
                }
            )
    return sources


def result_payload(result) -> Any:
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    text = "\n".join(getattr(c, "text", "") for c in result.content)
    with contextlib.suppress(json.JSONDecodeError):
        return json.loads(text)
    return text


# --- LLM : une seule interface, LiteLLM en vrai, un script en mode démo ----------------------


async def litellm_stream(turn: Turn, messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
    """Émet {"token": str} au fil de l'eau, puis {"final": message, "usage": ..., "cost": ...}."""
    try:
        stream = await litellm.acompletion(
            model=turn.model,
            messages=messages,
            tools=tools,
            api_key=turn.api_key,
            api_base=turn.api_base,
            stream=True,
            **({"num_ctx": OLLAMA_NUM_CTX} if turn.model.startswith("ollama") else {}),
            stream_options={"include_usage": True},
        )
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
            if chunk.choices and (delta := chunk.choices[0].delta) and delta.content:
                yield {"token": delta.content}
    except Exception as exc:
        raise classify_error(exc, turn.api_key) from exc

    full = litellm.stream_chunk_builder(chunks, messages=messages)
    cost = 0.0
    with contextlib.suppress(Exception):  # modèle absent de la grille de prix LiteLLM
        cost = litellm.completion_cost(completion_response=full)
    yield {"final": full.choices[0].message.model_dump(exclude_none=True), "usage": full.usage, "cost": cost}


async def demo_stream(turn: Turn, messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]:
    """Faux LLM sans clé : appelle vraiment les outils MCP, puis résume leurs résultats.

    Sert à tester l'interface de bout en bout ; il ne « comprend » rien.
    """
    last = messages[-1]
    if last["role"] == "user":
        cinema = re.search(r"film|cin[ée]ma|movie|réalis", last["content"], re.I)
        name = "search_films" if cinema else "search_debats"
        call = {
            "id": "demo-1",
            "type": "function",
            "function": {
                "name": name,
                "arguments": json.dumps({"query": last["content"], "limit": 4}, ensure_ascii=False),
            },
        }
        yield {"final": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": None, "cost": 0.0}
        return
    results = json.loads(last["content"]) if last["content"].startswith(("[", "{")) else []
    lines = ["*Mode démo : pas de vrai LLM, je liste simplement ce que les outils ont trouvé.*", ""]
    for r in results if isinstance(results, list) else []:
        if "title" in r:
            lines.append(f"- **{r['title']}** ({r.get('year')}) — {r.get('summary') or ''}"[:300])
        else:
            lines.append(f"- **{r.get('orateur')}**, {r.get('date')} — {r.get('sujet') or r.get('section')}")
    text = "\n".join(lines) if len(lines) > 2 else "Les outils n'ont rien trouvé."
    for i in range(0, len(text), 12):
        yield {"token": text[i : i + 12]}
    yield {"final": {"role": "assistant", "content": text}, "usage": None, "cost": 0.0}


# --- Boucle agent ----------------------------------------------------------------------------


def to_openai_tools(group) -> list[dict]:
    return [
        {"type": "function", "function": {"name": n, "description": t.description or "", "parameters": t.input_schema}}
        for n, t in group.tools.items()
    ]


async def run_turn(group, turn: Turn, tool_servers: dict[str, str], llm=litellm_stream) -> AsyncIterator[dict]:
    """Répond à un message ; émet les événements affichés par l'interface (et par la CLI)."""
    t_start = time.perf_counter()
    tools = to_openai_tools(group)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *turn.history, {"role": "user", "content": turn.message}]
    stats = {"llm_calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
    stats |= {"llm_ms": 0, "tool_ms": 0}

    for round_ in range(1, MAX_TOOL_ROUNDS + 1):
        yield {"type": "thinking", "round": round_}
        t0 = time.perf_counter()
        final = None
        async for ev in llm(turn, messages, tools):
            if "token" in ev:
                yield {"type": "token", "text": ev["token"]}
            else:
                final = ev
        stats["llm_ms"] += int((time.perf_counter() - t0) * 1000)
        stats["llm_calls"] += 1
        if final["usage"]:
            stats["prompt_tokens"] += final["usage"].prompt_tokens or 0
            stats["completion_tokens"] += final["usage"].completion_tokens or 0
        stats["cost_usd"] += final["cost"] or 0.0

        msg = final["final"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            stats["total_ms"] = int((time.perf_counter() - t_start) * 1000)
            yield {"type": "done", "content": msg.get("content") or "", "stats": stats}
            return

        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool_call", "id": call["id"], "name": name, "server": tool_servers.get(name), "args": args}
            t0 = time.perf_counter()
            try:
                result = await group.call_tool(name, args)
                ok, payload = not result.is_error, result_payload(result)
            except Exception as exc:  # outil inconnu, serveur tombé, arguments invalides…
                ok, payload = False, {"error": str(exc)}
            ms = int((time.perf_counter() - t0) * 1000)
            stats["tool_ms"] += ms
            stats["tool_calls"] += 1
            sources = extract_sources(name, payload) if ok else []
            yield {
                "type": "tool_result",
                "id": call["id"],
                "name": name,
                "ok": ok,
                "duration_ms": ms,
                "count": len(payload) if isinstance(payload, list) else 1,
                "sources": sources,
                "error": None if ok else str(payload)[:300],
            }
            content = json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})

    stats["total_ms"] = int((time.perf_counter() - t_start) * 1000)
    yield {"type": "error", "kind": "max_rounds", "message": "Trop d'appels d'outils sans réponse finale."}


SERVER_MODULES = {"cinema": "agora.servers.cinema", "assemblee": "agora.servers.assemblee"}


async def connect_servers(group, urls: dict[str, str] | None = None) -> dict[str, str]:
    """Connecte les serveurs MCP (stdio par défaut, HTTP si URL) ; renvoie outil → serveur."""
    import sys

    from mcp.client.session_group import StreamableHttpParameters
    from mcp.client.stdio import StdioServerParameters

    tool_servers: dict[str, str] = {}
    for server, module in SERVER_MODULES.items():
        before = set(group.tools)
        if urls and server in urls:
            params = StreamableHttpParameters(url=urls[server])
        else:
            params = StdioServerParameters(command=sys.executable, args=["-m", module], cwd=str(ROOT))
        await group.connect_to_server(params)
        tool_servers |= dict.fromkeys(set(group.tools) - before, server)
    return tool_servers
