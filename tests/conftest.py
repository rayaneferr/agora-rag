"""Fixtures : Qdrant en mémoire + embedder factice, pour tester les outils MCP sans Docker ni bge-m3."""

import hashlib
import math
import re
from pathlib import Path

import polars as pl
import pytest
from qdrant_client import QdrantClient

from agora.contexts.assemblee import ingestion as ing_an
from agora.contexts.assemblee import server as srv_an
from agora.contexts.cinema import ingestion as ing_cinema
from agora.contexts.cinema import server as srv_cinema

DIM = 256


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
def qdrant_memory(monkeypatch):
    client = QdrantClient(":memory:")

    ing_cinema.ensure_collection(client, DIM)
    ing_cinema.index(client, ing_cinema.build_points(FILMS), embed_fn=fake_embed)

    ing_an.ensure_collection(client, DIM)
    seance = (Path(__file__).parent / "fixtures" / "seance.xml").read_bytes()
    items = [chunk for inter in ing_an.parse_seance(seance) for chunk in ing_an.to_chunks(inter)]
    ing_an.index(client, items, embed_fn=fake_embed)

    for module in (srv_cinema, srv_an):
        monkeypatch.setattr(module, "qdrant", lambda: client)
        monkeypatch.setattr(module, "embed", fake_embed)
    srv_an._orateurs.cache_clear()
    yield client
    srv_an._orateurs.cache_clear()
