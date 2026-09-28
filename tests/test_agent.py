"""Boucle agent de bout en bout : LLM de démo + vrais serveurs MCP (en mémoire)."""

from contextlib import AsyncExitStack

import pytest
from mcp import Client

from agora.agent import Turn, demo_stream, extract_sources, run_turn, scrub
from agora.servers.assemblee import mcp as mcp_assemblee
from agora.servers.cinema import mcp as mcp_cinema


class InMemoryGroup:
    """Même interface que ClientSessionGroup (tools + call_tool), sur des clients MCP en mémoire."""

    def __init__(self):
        self.tools, self._clients, self._stack = {}, {}, AsyncExitStack()

    async def __aenter__(self):
        for server in (mcp_cinema, mcp_assemblee):
            client = await self._stack.enter_async_context(Client(server))
            for tool in (await client.list_tools()).tools:
                self.tools[tool.name], self._clients[tool.name] = tool, client
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def call_tool(self, name, args):
        return await self._clients[name].call_tool(name, args)


async def collect(message: str) -> list[dict]:
    async with InMemoryGroup() as group:
        turn = Turn(model="demo/scripted", api_key=None, message=message)
        return [ev async for ev in run_turn(group, turn, {}, llm=demo_stream)]


@pytest.mark.usefixtures("qdrant_memory")
async def test_tour_complet_films():
    events = await collect("Un film sur un présentateur météo qui revit la même journée")
    types = [e["type"] for e in events]
    assert types[0] == "thinking" and types[-1] == "done"
    assert types.index("tool_call") < types.index("tool_result") < types.index("token")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["ok"] and result["name"] == "search_films"
    assert {s["kind"] for s in result["sources"]} == {"film"}
    done = events[-1]
    assert done["stats"]["tool_calls"] == 1 and done["stats"]["llm_calls"] == 2
    assert "Groundhog Day" in done["content"]


@pytest.mark.usefixtures("qdrant_memory")
async def test_tour_complet_debats():
    events = await collect("Qu'a dit la ministre sur la protection des mineurs ?")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["name"] == "search_debats"
    assert all(s["kind"] == "debat" and s["url"] for s in result["sources"])


@pytest.mark.usefixtures("qdrant_memory")
async def test_outil_en_erreur_ne_casse_pas_le_tour():
    async def llm_outil_inconnu(turn, messages, tools):
        if messages[-1]["role"] == "user":
            call = {"id": "x", "type": "function", "function": {"name": "outil_inexistant", "arguments": "{}"}}
            yield {"final": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": None, "cost": 0.0}
        else:
            yield {"final": {"role": "assistant", "content": "Désolé."}, "usage": None, "cost": 0.0}

    async with InMemoryGroup() as group:
        turn = Turn(model="x", api_key=None, message="?")
        events = [ev async for ev in run_turn(group, turn, {}, llm=llm_outil_inconnu)]
    result = next(e for e in events if e["type"] == "tool_result")
    assert not result["ok"] and result["error"]
    assert events[-1]["type"] == "done"


def test_scrub_masque_les_cles():
    assert "sk-abcdefghijkl" not in scrub("Incorrect API key provided: sk-abcdefghijkl", None)
    assert scrub("clé=secret123", "secret123") == "clé=sk-***"


def test_extract_sources_ignore_les_erreurs():
    assert extract_sources("get_film", {"error": "introuvable"}) == []
    films = extract_sources("search_films", [{"title": "Alien", "year": 1979, "wiki_url": "u", "summary": "s"}])
    assert films[0] | {"score": None} == {
        "kind": "film",
        "title": "Alien",
        "subtitle": "1979",
        "url": "u",
        "excerpt": "s",
        "score": None,
    }
