"""Boucle agent : le modèle appelle les outils du contexte jusqu'à pouvoir répondre.

Tout ce qui se passe est émis sous forme d'événements (réflexion, appels d'outils, sources, texte,
statistiques), pour que l'interface montre en direct ce que fait l'agent. Aucune dépendance
d'infrastructure : le modèle et les outils arrivent par les ports.
"""

import json
import re
import time
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field

from agora.core.context import ContextSpec
from agora.core.ports import LLMPort, ToolGateway

MAX_TOOL_ROUNDS = 8

COMMON_RULES = """
Règles communes :
- Appuie-toi sur tes outils plutôt que sur ta mémoire ; si les résultats sont décevants, reformule ou relance.
- N'ajoute pas de filtre que l'utilisateur n'a pas demandé. Si une recherche filtrée ne renvoie rien,
  relance-la avec moins de filtres avant de conclure.
- Cite tes sources. Si les outils ne trouvent rien, dis-le au lieu d'inventer.
- Réponds en français, de façon claire et structurée (Markdown)."""


@dataclass
class Turn:
    """Un message utilisateur à traiter, avec l'historique de la conversation."""

    message: str
    history: list[dict] = field(default_factory=list)  # [{"role": "user"|"assistant", "content": str}]


class LLMError(Exception):
    """Erreur côté modèle, avec un message présentable à l'utilisateur."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def scrub(text: str, secret: str | None = None) -> str:
    """Une clé ne doit jamais ressortir dans un message d'erreur ou un log."""
    if secret:
        text = text.replace(secret, "sk-***")
    return re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", text)


async def run_turn(context: ContextSpec, llm: LLMPort, tools: ToolGateway, turn: Turn) -> AsyncIterator[dict]:
    """Répond à un message ; émet les événements affichés par l'interface (et par la CLI)."""
    t_start = time.perf_counter()
    schemas = tools.tool_schemas()
    system = context.system_prompt.strip() + "\n" + COMMON_RULES
    messages = [{"role": "system", "content": system}, *turn.history, {"role": "user", "content": turn.message}]
    stats = {"llm_calls": 0, "tool_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}
    stats |= {"llm_ms": 0, "tool_ms": 0}

    for round_ in range(1, MAX_TOOL_ROUNDS + 1):
        yield {"type": "thinking", "round": round_}
        t0 = time.perf_counter()
        final = None
        async for ev in llm(messages, schemas):
            if "token" in ev:
                yield {"type": "token", "text": ev["token"]}
            else:
                final = ev
        stats["llm_ms"] += int((time.perf_counter() - t0) * 1000)
        stats["llm_calls"] += 1
        if usage := final.get("usage"):
            stats["prompt_tokens"] += usage.get("prompt_tokens") or 0
            stats["completion_tokens"] += usage.get("completion_tokens") or 0
        stats["cost_usd"] += final.get("cost") or 0.0

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
            yield {
                "type": "tool_call",
                "id": call["id"],
                "name": name,
                "label": context.tool_labels.get(name, name),
                "args": args,
            }
            t0 = time.perf_counter()
            try:
                ok, payload = await tools.call(name, args)
            except Exception as exc:  # outil inconnu, serveur tombé, arguments invalides…
                ok, payload = False, {"error": str(exc)}
            ms = int((time.perf_counter() - t0) * 1000)
            stats["tool_ms"] += ms
            stats["tool_calls"] += 1
            sources = [asdict(s) for s in context.to_sources(name, payload)] if ok else []
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
            content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})

    yield {"type": "error", "kind": "max_rounds", "message": "Trop d'appels d'outils sans réponse finale."}
