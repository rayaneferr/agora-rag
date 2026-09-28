"""Serveur MCP « cinema » : RAG sur les synopsis Wikipedia (~35k films)."""

from qdrant_client import models

from mcp.server.mcpserver import MCPServer
from agora.common import COLLECTION_FILMS, embed, qdrant, warm_up

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
        year_min: année de sortie minimale.
        year_max: année de sortie maximale.
        limit: nombre de films à retourner (1-20).
    """
    must: list[models.Condition] = []
    if genre:
        must.append(models.FieldCondition(key="genre", match=models.MatchText(text=genre)))
    if director:
        must.append(models.FieldCondition(key="director", match=models.MatchText(text=director)))
    if year_min or year_max:
        must.append(models.FieldCondition(key="year", range=models.Range(gte=year_min, lte=year_max)))

    # Plusieurs chunks d'un même film peuvent matcher : on groupe par film_id.
    groups = qdrant().query_points_groups(
        COLLECTION_FILMS,
        query=embed([query])[0],
        group_by="film_id",
        limit=max(1, min(limit, 20)),
        group_size=1,
        query_filter=models.Filter(must=must) if must else None,
        with_payload=True,
    ).groups
    results = []
    for g in groups:
        hit = g.hits[0]
        p = hit.payload
        results.append(
            {
                "film_id": p["film_id"],
                "title": p["title"],
                "year": p["year"],
                "director": p["director"],
                "genre": p["genre"],
                "cast": p["cast"],
                "score": round(hit.score, 3),
                "summary": p["summary"],
                "matching_excerpt": p["text"][:600],
                "wiki_url": p["wiki_url"],
            }
        )
    return results


@mcp.tool()
def get_film(film_id: int) -> dict:
    """Retourne la fiche complète d'un film (synopsis intégral), à partir du film_id de search_films."""
    points, _ = qdrant().scroll(
        COLLECTION_FILMS,
        scroll_filter=models.Filter(must=[models.FieldCondition(key="film_id", match=models.MatchValue(value=film_id))]),
        limit=100,
        with_payload=True,
    )
    if not points:
        return {"error": f"film_id {film_id} introuvable"}
    chunks = sorted((p.payload for p in points), key=lambda p: p["chunk_index"])
    fiche = {k: v for k, v in chunks[0].items() if k not in {"text", "chunk_index"}}
    fiche["plot"] = "\n".join(c["text"] for c in chunks)
    return fiche


def main() -> None:
    warm_up()
    mcp.run("stdio")


if __name__ == "__main__":
    main()
