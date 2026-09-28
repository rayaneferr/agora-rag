"""Serveur MCP « cinema » : RAG sur les synopsis Wikipedia (~35k films)."""

from mcp.server.mcpserver import MCPServer

from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.mcp_serve import serve
from agora.contexts.cinema import COLLECTION
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


def main() -> None:
    serve(mcp, default_port=8101)


if __name__ == "__main__":
    main()
