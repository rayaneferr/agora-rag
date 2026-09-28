"""Serveur MCP « cinema » : RAG sur les synopsis Wikipedia (~35k films)."""

from mcp.server.mcpserver import MCPServer

from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.mcp_serve import archives, guided_prompt, serve
from agora.contexts.cinema import COLLECTION, SPEC
from agora.core.text import join_chunks

mcp = MCPServer(
    "cinema",
    log_level="WARNING",
    instructions=(
        "Base de ~35k films (synopsis Wikipedia, en anglais). Utilise search_films pour trouver des films "
        "à partir d'une description d'intrigue, d'un thème ou de critères, puis get_film pour le synopsis complet."
    ),
)


@mcp.tool()
def search_films(
    query: str,
    genre: str | None = None,
    director: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    limit: int = 5,
) -> list[dict]:
    """Recherche sémantique de films par intrigue, thème ou ambiance.

    Args:
        query: description libre de ce qu'on cherche (ex. « un homme revit la même journée en boucle »).
            Les synopsis sont en anglais ; une requête en anglais donne souvent de meilleurs résultats.
        genre: filtre texte sur le genre (ex. « comedy », « horror »).
        director: filtre texte sur le réalisateur (ex. « Nolan »).
        year_min: année de sortie minimale (seulement si l'utilisateur précise une période).
        year_max: année de sortie maximale (seulement si l'utilisateur précise une période).
        limit: nombre de films à retourner (1-20).
    """
    n = max(1, min(limit, 20))
    where = []
    if genre:
        where.append(f"lower(genre) LIKE {vs.quote(f'%{genre.lower()}%')}")
    if director:
        where.append(f"lower(director) LIKE {vs.quote(f'%{director.lower()}%')}")
    if year_min:
        where.append(f"year >= {int(year_min)}")
    if year_max:
        where.append(f"year <= {int(year_max)}")

    # Plusieurs chunks d'un même film peuvent matcher : on sur-échantillonne puis on garde le meilleur par film.
    hits = vs.search(COLLECTION, vs.embed([query])[0], " AND ".join(where) or None, limit=12 * n)
    results, seen = [], set()
    for p in hits:
        # Dédoublonne par film, et par (titre, année) : le dataset liste certains films sous deux « origines ».
        key = (p["title"].strip().lower(), p["year"])
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "film_id": p["film_id"],
                "title": p["title"].strip(),
                "year": p["year"],
                "director": p["director"],
                "genre": p["genre"],
                "cast": p["cast"],
                "score": round(p["score"], 3),
                "summary": p["summary"],
                "matching_excerpt": p["text"][:600],
                "wiki_url": p["wiki_url"],
            }
        )
        if len(results) == n:
            break
    return results


@mcp.tool()
def get_film(film_id: int) -> dict:
    """Retourne la fiche complète d'un film (synopsis intégral), à partir du film_id de search_films."""
    chunks = sorted(vs.select(COLLECTION, f"film_id = {int(film_id)}"), key=lambda p: p["chunk_index"])
    if not chunks:
        return {"error": f"film_id {film_id} introuvable"}
    fiche = {k: v for k, v in chunks[0].items() if k not in {"id", "text", "chunk_index"}}
    fiche["plot"] = join_chunks([c["text"] for c in chunks])
    return fiche


# Règles transmises à l'assistant de l'utilisateur par les prompts : c'est lui qui rédige la réponse.
RULES = [
    "Ne propose que des films renvoyés par les outils, jamais de mémoire.",
    "Cite chaque film avec son titre, son année et son lien Wikipédia.",
    "Formule les requêtes de search_films en anglais : c'est la langue des synopsis.",
    "Ne divulgâche pas la fin, sauf si on te le demande.",
    "Si rien ne correspond, dis-le en une phrase plutôt que d'inventer.",
]


@mcp.resource(
    "cinema://archives",
    title="Archives de La Salle obscure",
    description="Étendue des synopsis indexés, outils disponibles et exemples de questions.",
    mime_type="application/json",
)
def archives_cinema() -> dict:
    return archives(SPEC)


@mcp.prompt(
    name="trouver-un-film",
    title="Retrouver un film",
    description="Retrouve un film à partir d'une scène, d'une intrigue ou d'un souvenir flou.",
)
def trouver_un_film(souvenir: str) -> str:
    return guided_prompt(
        SPEC,
        f"Je cherche un film dont je me souviens ainsi : « {souvenir} ». Lequel est-ce ?",
        [
            "Traduis le souvenir en une description d'intrigue en anglais, et appelle search_films avec.",
            "Si plusieurs films sont plausibles, appelle get_film sur les meilleurs pour vérifier l'intrigue.",
            "Donne le film le plus probable et pourquoi il correspond, puis deux autres pistes au plus.",
        ],
        RULES,
    )


@mcp.prompt(
    name="recommander-des-films",
    title="Des films selon une envie",
    description="Des films qui correspondent à une envie, avec un genre et une période optionnels.",
)
def recommander_des_films(
    envie: str, genre: str | None = None, annee_min: str | None = None, annee_max: str | None = None
) -> str:
    given = {"genre": genre, "year_min": annee_min, "year_max": annee_max}
    filters = ", ".join(f"{k}={v}" for k, v in given.items() if v)
    return guided_prompt(
        SPEC,
        f"Propose-moi des films qui correspondent à cette envie : « {envie} ».",
        [
            "Appelle search_films avec l'envie reformulée en anglais"
            + (f" et les filtres {filters}" if filters else "")
            + " ; relance avec une autre formulation si les résultats sont décevants.",
            "Retiens cinq films au plus, les plus proches de l'envie.",
            "Une ligne par film : titre, année, et ce qui le rattache à l'envie.",
        ],
        RULES,
    )


@mcp.prompt(
    name="fiche-film",
    title="Fiche d'un film",
    description="L'intrigue d'un film précis, lue dans son synopsis complet.",
)
def fiche_film(titre: str) -> str:
    return guided_prompt(
        SPEC,
        f"Présente-moi le film « {titre} ».",
        [
            "Appelle search_films avec le titre pour obtenir son film_id ; en cas d'homonymes, demande lequel.",
            "Appelle get_film avec ce film_id pour lire le synopsis complet.",
            "Présente le film : année, réalisateur, genre, distribution principale, et l'intrigue sans la fin.",
        ],
        RULES,
    )


def main() -> None:
    serve(mcp, default_port=8101)


if __name__ == "__main__":
    main()
