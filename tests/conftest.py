"""Fixtures : LanceDB dans un dossier temporaire + embedder factice, pour tester les outils MCP sans bge-m3."""

import hashlib
import math
import re
from pathlib import Path

import polars as pl
import pytest
from mcp import Client

from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.mcp import decode
from agora.contexts.assemblee import ingestion as ing_an
from agora.contexts.assemblee import server as srv_an
from agora.contexts.assemblee.server import mcp as mcp_assemblee
from agora.contexts.cinema import ingestion as ing_cinema
from agora.contexts.cinema.server import mcp as mcp_cinema

DIM = 256
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

    @property
    def tool_names(self):
        return [t.name for t in self._tools]

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


def fake_embed(texts: list[str]) -> list[list[float]]:
    """Sac de mots haché : déterministe, et deux textes qui partagent des mots sont proches."""
    vectors = []
    for text in texts:
        v = [0.0] * DIM
        for word in re.findall(r"\w{3,}", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        vectors.append([x / norm for x in v])
    return vectors


FILMS = pl.DataFrame(
    {
        "film_id": [0, 1, 2, 3],
        "Release Year": ["1993", "2010", "1979", "1979"],
        "Title": ["Groundhog Day", "Inception", "Alien", " Alien"],  # doublon réel du dataset
        "Origin/Ethnicity": ["American", "American", "American", "British"],
        "Director": ["Harold Ramis", "Christopher Nolan", "Ridley Scott", "Ridley Scott"],
        "Cast": ["Bill Murray", "Leonardo DiCaprio", "Sigourney Weaver", "Sigourney Weaver"],
        "Genre": ["comedy, fantasy", "science fiction", "science fiction, horror", "science fiction, horror"],
        "Wiki Page": [f"https://en.wikipedia.org/wiki/{t}" for t in ("Groundhog_Day", "Inception", "Alien", "Alien")],
        "Plot": [
            "A weatherman finds himself living the same day over and over again in a small town.",
            "A thief who steals secrets through dream sharing is given the task of planting an idea.\n"
            + "The team descends into multiple layers of dreams. " * 60,
            "The crew of a spaceship is hunted by a deadly alien creature aboard their vessel.",
            "The crew of a spaceship is hunted by a deadly alien creature aboard their vessel.",
        ],
        "PlotSummary": ["Time loop comedy.", "Dream heist.", "Space horror.", "Space horror."],
    }
)


@pytest.fixture
def index(monkeypatch, tmp_path):
    monkeypatch.setattr(vs, "DB_DIR", tmp_path / "lancedb")
    monkeypatch.setattr(vs, "embed", fake_embed)
    vs.db.cache_clear()
    srv_an._orateurs.cache_clear()

    ing_cinema.ensure_table(DIM)
    ing_cinema.index(ing_cinema.build_points(FILMS))

    ing_an.ensure_table(DIM)
    seance = (Path(__file__).parent / "fixtures" / "seance.xml").read_bytes()
    ing_an.index([chunk for inter in ing_an.parse_seance(seance) for chunk in ing_an.to_chunks(inter)])

    yield vs.db()
    vs.db.cache_clear()
    srv_an._orateurs.cache_clear()
