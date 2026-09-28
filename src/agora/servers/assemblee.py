"""Serveur MCP « assemblee » : RAG sur les comptes rendus de séance de l'Assemblée nationale (17e lég.)."""

import unicodedata
from datetime import date
from functools import lru_cache

from mcp.server.mcpserver import MCPServer
from qdrant_client import models

from agora.common import COLLECTION_DEBATS, embed, join_chunks, qdrant
from agora.servers._run import serve

mcp = MCPServer(
    "assemblee",
    log_level="WARNING",
    instructions=(
        "Comptes rendus des séances publiques de l'Assemblée nationale (17e législature, depuis juillet 2024). "
        "Pour une question sur une personne, appelle d'abord find_orateurs pour obtenir son nom exact, "
        "puis search_debats avec le filtre orateur. Cite toujours l'orateur, la date et l'URL de la séance."
    ),
)


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


@lru_cache
def _orateurs() -> dict[str, int]:
    facets = qdrant().facet(COLLECTION_DEBATS, key="orateur", limit=5000, exact=True)
    return {h.value: h.count for h in facets.hits}


def _date_int(d: str | None) -> int | None:
    return int(date.fromisoformat(d).strftime("%Y%m%d")) if d else None


def _format(p: dict, score: float | None = None) -> dict:
    out = {
        "orateur": p["orateur"],
        # Groupe seulement quand le compte rendu l'indique ; le référentiel complet des députés viendra en v0.6.
        "groupe": p.get("groupe"),
        "qualite": p["qualite"] or None,
        "date": p["date"],
        "sujet": p["sujet"],
        "section": p["section"],
        "texte": p["text"],
        "seance_uid": p["seance_uid"],
        "ordre": p["ordre"],
        "url": p["url"],
    }
    if score is not None:
        out["score"] = round(score, 3)
    return out


@mcp.tool()
def find_orateurs(nom: str, limit: int = 10) -> list[dict]:
    """Trouve le nom exact d'un orateur (député ou ministre) tel qu'il apparaît dans les comptes rendus.

    Args:
        nom: nom ou partie du nom, sans accent ni civilité nécessaire (ex. « coquerel », « Panosyan »).
        limit: nombre maximal de résultats.
    """
    needle = _fold(nom)
    matches = [(o, n) for o, n in _orateurs().items() if needle in _fold(o)]
    matches.sort(key=lambda x: -x[1])
    return [{"orateur": o, "nb_interventions": n} for o, n in matches[:limit]]


@mcp.tool()
def search_debats(
    query: str,
    orateur: str | None = None,
    date_min: str | None = None,
    date_max: str | None = None,
    limit: int = 8,
) -> list[dict]:
    """Recherche sémantique dans les interventions en séance publique.

    Args:
        query: sujet ou question en langage naturel (ex. « réforme des retraites, âge légal »).
        orateur: nom EXACT de l'orateur, obtenu via find_orateurs (ex. « Éric Coquerel », sans civilité).
        date_min: date minimale incluse, format AAAA-MM-JJ.
        date_max: date maximale incluse, format AAAA-MM-JJ.
        limit: nombre d'extraits à retourner (1-20).
    """
    must: list[models.Condition] = []
    if orateur:
        must.append(models.FieldCondition(key="orateur", match=models.MatchValue(value=orateur)))
    if date_min or date_max:
        must.append(
            models.FieldCondition(key="date_int", range=models.Range(gte=_date_int(date_min), lte=_date_int(date_max)))
        )
    hits = (
        qdrant()
        .query_points(
            COLLECTION_DEBATS,
            query=embed([query])[0],
            limit=max(1, min(limit, 20)),
            query_filter=models.Filter(must=must) if must else None,
            with_payload=True,
        )
        .points
    )
    return [_format(h.payload, h.score) for h in hits]


@mcp.tool()
def get_contexte(seance_uid: str, ordre: int, avant: int = 3, apres: int = 3) -> list[dict]:
    """Retourne les interventions qui entourent un extrait (qui a répondu quoi), dans l'ordre de la séance.

    Args:
        seance_uid: identifiant de séance renvoyé par search_debats.
        ordre: position de l'extrait dans la séance, renvoyée par search_debats.
        avant: nombre d'interventions précédentes.
        apres: nombre d'interventions suivantes.
    """
    points, _ = qdrant().scroll(
        COLLECTION_DEBATS,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(key="seance_uid", match=models.MatchValue(value=seance_uid)),
                # L'ordre est la position du paragraphe dans la séance, pas un rang d'intervention :
                # on prend une fenêtre large puis on coupe.
                models.FieldCondition(key="ordre", range=models.Range(gte=ordre - 60, lte=ordre + 60)),
            ]
        ),
        limit=500,
        with_payload=True,
    )
    # Recolle les chunks d'une même intervention.
    by_ordre: dict[int, list[dict]] = {}
    for p in sorted((p.payload for p in points), key=lambda p: (p["ordre"], p["chunk_index"])):
        by_ordre.setdefault(p["ordre"], []).append(p)
    rows = [{**chunks[0], "text": join_chunks([c["text"] for c in chunks])} for chunks in by_ordre.values()]
    idx = next((i for i, p in enumerate(rows) if p["ordre"] >= ordre), len(rows))
    return [_format(p) for p in rows[max(0, idx - avant) : idx + apres + 1]]


def main() -> None:
    serve(mcp, default_port=8102)


if __name__ == "__main__":
    main()
