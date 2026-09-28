"""Outils MCP testés à travers le protocole (client MCP en mémoire), pas en appel Python direct."""

import json

import pytest
from mcp import Client

from agora.contexts.assemblee.server import mcp as mcp_assemblee
from agora.contexts.cinema.server import mcp as mcp_cinema

pytestmark = pytest.mark.usefixtures("index")


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


async def test_filtres_echappes():
    # Les filtres viennent du modèle : une apostrophe ne doit ni casser ni détourner la requête SQL.
    assert await call(mcp_cinema, "search_films", query="alien", director="O'Brien' OR '1'='1") == []
    assert await call(mcp_assemblee, "search_debats", query="budget", orateur="d'Artagnan") == []
    films = await call(mcp_cinema, "search_films", query="alien", director="scott", year_min=1970, year_max=1980)
    assert [f["title"] for f in films] == ["Alien"]


async def prompt(server, name: str, **args) -> str:
    async with Client(server) as client:
        result = await client.get_prompt(name, args)
    return result.messages[0].content.text


async def test_prompts_exposes():
    async with Client(mcp_cinema) as c:
        names = {p.name for p in (await c.list_prompts()).prompts}
        assert names == {"trouver-un-film", "recommander-des-films", "fiche-film"}
    async with Client(mcp_assemblee) as c:
        names = {p.name for p in (await c.list_prompts()).prompts}
        assert names == {"position-orateur", "debat-sur-un-sujet", "qui-a-repondu"}


async def test_prompt_guide_les_outils_et_donne_l_etendue():
    text = await prompt(mcp_assemblee, "position-orateur", orateur="Dubois", sujet="l'école")
    assert "find_orateurs" in text and "search_debats" in text
    # L'étendue vient de l'index : le modèle de l'utilisateur sait où s'arrêtent les archives.
    assert "séances du 6 novembre 2024 au 6 novembre 2024" in text
    assert "Règles :" in text


async def test_prompt_arguments_optionnels():
    sans = await prompt(mcp_assemblee, "debat-sur-un-sujet", sujet="budget")
    avec = await prompt(mcp_assemblee, "debat-sur-un-sujet", sujet="budget", date_min="2025-01-01")
    assert "date_min" not in sans and "date_min=2025-01-01" in avec
    films = await prompt(mcp_cinema, "recommander-des-films", envie="angoisse spatiale", genre="horror")
    assert "genre=horror" in films and "year_min" not in films


async def test_resource_archives():
    async with Client(mcp_cinema) as client:
        result = await client.read_resource("cinema://archives")
    archives = json.loads(result.contents[0].text)
    assert archives["guide"] == "Lumière"
    assert archives["etendue"] == "films sortis de 1979 à 2010"
    assert archives["extraits_indexes"] > 0
    assert set(archives["outils"]) == {"search_films", "get_film"}
