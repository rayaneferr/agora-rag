"""Boucle agent de bout en bout : LLM de démo + vrai serveur MCP du contexte (en mémoire)."""

import pytest
from conftest import SERVERS, InMemoryGateway

from agora.adapters.outbound import llm
from agora.contexts import CONTEXTS
from agora.contexts.assemblee import to_sources as sources_an
from agora.contexts.cinema import to_sources as sources_cinema
from agora.contexts.cinema.server import mcp as mcp_cinema
from agora.core.agent import LLMError, Turn, run_turn, system_prompt

CINEMA = CONTEXTS["cinema"]


class _SansRecherche:
    """Passerelle sans outil de recherche : le mode démo ne doit pas appeler un outil « None »."""

    def tool_schemas(self):
        return [{"type": "function", "function": {"name": "get_film", "parameters": {}}}]

    async def call(self, name, args):
        raise AssertionError("aucun outil ne devrait être appelé")


async def collect(context: str, message: str, model=None) -> list[dict]:
    async with InMemoryGateway(SERVERS[context]) as gateway:
        return [ev async for ev in run_turn(CONTEXTS[context], model or llm.demo(), gateway, Turn(message))]


@pytest.mark.usefixtures("index")
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


@pytest.mark.usefixtures("index")
async def test_chaque_agent_ne_voit_que_les_outils_de_son_contexte():
    async with InMemoryGateway(mcp_cinema) as g:
        assert {t["function"]["name"] for t in g.tool_schemas()} == {"search_films", "get_film"}
    events = await collect("assemblee", "protection des mineurs en ligne")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["name"] == "search_debats"
    assert all(s["kind"] == "seance" and s["url"] for s in result["sources"])


@pytest.mark.usefixtures("index")
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


def test_prompt_systeme_annonce_l_etendue_des_archives():
    prompt = system_prompt(CONTEXTS["assemblee"], "séances du 18 juillet 2024 au 26 septembre 2026")
    assert "Étendue des archives : séances du 18 juillet 2024 au 26 septembre 2026." in prompt
    assert "Règles communes" in prompt
    assert "Étendue" not in system_prompt(CONTEXTS["assemblee"])


async def test_flux_coupe_avant_le_message_final():
    def llm_muet():
        async def stream(messages, tools):
            yield {"token": "Je commence…"}

        return stream

    with pytest.raises(LLMError) as exc:
        async for _ in run_turn(CINEMA, llm_muet(), _SansRecherche(), Turn("?")):
            pass
    assert exc.value.kind == "stream"


async def test_demo_sans_outil_de_recherche_repond_quand_meme():
    events = [ev async for ev in run_turn(CINEMA, llm.demo(), _SansRecherche(), Turn("?"))]
    assert events[-1]["type"] == "done"


def test_sources_ignorent_erreurs_et_resultats_non_citables():
    assert sources_cinema("get_film", {"error": "introuvable"}) == []
    assert sources_an("find_orateurs", [{"orateur": "Éric Coquerel", "nb_interventions": 3}]) == []
    film = sources_cinema("search_films", [{"title": "Alien", "year": 1979, "wiki_url": "u", "summary": "s"}])[0]
    assert (film.title, film.subtitle, film.url) == ("Alien", "1979", "u")
