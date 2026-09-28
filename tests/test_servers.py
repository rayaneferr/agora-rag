"""Outils MCP testés à travers le protocole (client MCP en mémoire), pas en appel Python direct."""

import json

import pytest
from mcp import Client

from agora.servers.assemblee import mcp as mcp_assemblee
from agora.servers.cinema import mcp as mcp_cinema

pytestmark = pytest.mark.usefixtures("qdrant_memory")


async def call(server, tool: str, **args):
    async with Client(server) as client:
        result = await client.call_tool(tool, args)
    assert not result.is_error, result.content
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)  # dict non typé : renvoyé en JSON texte


async def test_outils_exposes():
    async with Client(mcp_cinema) as c:
        assert {t.name for t in (await c.list_tools()).tools} == {"search_films", "get_film"}
    async with Client(mcp_assemblee) as c:
        assert {t.name for t in (await c.list_tools()).tools} == {"find_orateurs", "search_debats", "get_contexte"}


async def test_search_films_classe_le_bon_film_en_tete():
    films = await call(mcp_cinema, "search_films", query="weatherman living the same day again")
    assert films[0]["title"] == "Groundhog Day"


async def test_search_films_un_resultat_par_film():
    films = await call(mcp_cinema, "search_films", query="dreams layers dream sharing", limit=10)
    titles = [f["title"] for f in films]
    assert len(titles) == len(set(titles)) == 3


async def test_search_films_filtres():
    films = await call(mcp_cinema, "search_films", query="film", genre="horror")
    assert [f["title"] for f in films] == ["Alien"]
    films = await call(mcp_cinema, "search_films", query="film", year_min=2000)
    assert [f["title"] for f in films] == ["Inception"]


async def test_get_film_recolle_les_chunks():
    film = await call(mcp_cinema, "get_film", film_id=1)
    assert film["title"] == "Inception"
    assert film["plot"].startswith("A thief")
    assert film["plot"].count("multiple layers of dreams") == 60


async def test_get_film_inconnu():
    assert "error" in await call(mcp_cinema, "get_film", film_id=999)


async def test_find_orateurs_insensible_aux_accents_et_a_la_casse():
    res = await call(mcp_assemblee, "find_orateurs", nom="DUBOIS")
    assert res == [{"orateur": "Claire Dubois", "nb_interventions": 2}]


async def test_search_debats_filtre_orateur():
    res = await call(mcp_assemblee, "search_debats", query="enseignants", orateur="Claire Dubois")
    assert res and all(r["orateur"] == "Claire Dubois" for r in res)


async def test_search_debats_filtre_dates():
    assert await call(mcp_assemblee, "search_debats", query="réseaux", date_min="2025-01-01") == []
    assert await call(mcp_assemblee, "search_debats", query="réseaux", date_max="2024-12-31")


async def test_get_contexte_ordre_chronologique():
    res = await call(mcp_assemblee, "get_contexte", seance_uid="CRSANR5L17S2025O1N999", ordre=11, avant=1, apres=1)
    assert [r["orateur"] for r in res] == ["Alice Martin", "Claire Dubois", "Bruno Petit"]


async def test_search_films_dedoublonne_titre_annee():
    films = await call(mcp_cinema, "search_films", query="spaceship alien creature", limit=10)
    assert [f["title"] for f in films].count("Alien") == 1


async def test_search_debats_expose_le_groupe():
    res = await call(mcp_assemblee, "search_debats", query="publicité ciblée enfants", orateur="Denis Roux")
    assert res[0]["groupe"] == "RN"
    assert res[0]["section"] == "Protection des enfants" and res[0]["sujet"] == "Article 11"
