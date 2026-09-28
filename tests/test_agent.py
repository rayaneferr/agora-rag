"""Boucle agent de bout en bout : LLM de démo + vrai serveur MCP du contexte (en mémoire)."""

import pytest
from mcp import Client

from agora.adapters.outbound import llm
from agora.adapters.outbound.mcp import decode
from agora.contexts import CONTEXTS
from agora.contexts.assemblee import to_sources as sources_an
from agora.contexts.assemblee.server import mcp as mcp_assemblee
from agora.contexts.cinema import to_sources as sources_cinema
from agora.contexts.cinema.server import mcp as mcp_cinema
from agora.core.agent import Turn, run_turn, scrub

SERVERS = {"cinema": mcp_cinema, "assemblee": mcp_assemblee}


class InMemoryGateway:
    """Implémente ToolGateway sur un client MCP en mémoire : le cœur ne voit pas la différence."""

    def __init__(self, server):
        self._server = server

    async def __aenter__(self):
        self._cm = Client(self._server)
        self._client = await self._cm.__aenter__()
        self._tools = (await self._client.list_tools()).tools
        return self

    async def __aexit__(self, *exc):
        await self._cm.__aexit__(*exc)

    def tool_schemas(self):
        return [
            {
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
            }
            for t in self._tools
        ]

    async def call(self, name, args):
        result = await self._client.call_tool(name, args)
        return not result.is_error, decode(result)


async def collect(context: str, message: str, model=None) -> list[dict]:
    async with InMemoryGateway(SERVERS[context]) as gateway:
        return [ev async for ev in run_turn(CONTEXTS[context], model or llm.demo(), gateway, Turn(message))]


@pytest.mark.usefixtures("qdrant_memory")
async def test_tour_complet_cinema():
    events = await collect("cinema", "a weatherman living the same day over and over")
    types = [e["type"] for e in events]
    assert types[0] == "thinking" and types[-1] == "done"
    assert types.index("tool_call") < types.index("tool_result") < types.index("token")
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["label"] == "Recherche dans les synopsis"
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ok"] and {s["kind"] for s in result["sources"]} == {"film"}
    assert events[-1]["stats"]["tool_calls"] == 1 and "Groundhog Day" in events[-1]["content"]


@pytest.mark.usefixtures("qdrant_memory")
async def test_chaque_agent_ne_voit_que_les_outils_de_son_contexte():
    async with InMemoryGateway(mcp_cinema) as g:
        assert {t["function"]["name"] for t in g.tool_schemas()} == {"search_films", "get_film"}
    events = await collect("assemblee", "protection des mineurs en ligne")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["name"] == "search_debats"
    assert all(s["kind"] == "seance" and s["url"] for s in result["sources"])


@pytest.mark.usefixtures("qdrant_memory")
async def test_outil_en_erreur_ne_casse_pas_le_tour():
    def llm_outil_inconnu():
        async def stream(messages, tools):
            if messages[-1]["role"] == "user":
                call = {"id": "x", "type": "function", "function": {"name": "outil_inexistant", "arguments": "{}"}}
                yield {"final": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": None}
            else:
                yield {"final": {"role": "assistant", "content": "Désolé."}, "usage": None}

        return stream

    events = await collect("cinema", "?", model=llm_outil_inconnu())
    result = next(e for e in events if e["type"] == "tool_result")
    assert not result["ok"] and result["error"]
    assert events[-1]["type"] == "done"


def test_prompt_systeme_propre_au_contexte():
    assert "Lumière" in CONTEXTS["cinema"].system_prompt
    assert "Huissier" in CONTEXTS["assemblee"].system_prompt


def test_scrub_masque_les_cles():
    assert "sk-abcdefghijkl" not in scrub("Incorrect API key provided: sk-abcdefghijkl")
    assert scrub("clé=secret123", "secret123") == "clé=sk-***"


def test_sources_ignorent_erreurs_et_resultats_non_citables():
    assert sources_cinema("get_film", {"error": "introuvable"}) == []
    assert sources_an("find_orateurs", [{"orateur": "Éric Coquerel", "nb_interventions": 3}]) == []
    film = sources_cinema("search_films", [{"title": "Alien", "year": 1979, "wiki_url": "u", "summary": "s"}])[0]
    assert (film.title, film.subtitle, film.url) == ("Alien", "1979", "u")
