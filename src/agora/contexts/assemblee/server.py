"""Serveur MCP « assemblee » : RAG sur les comptes rendus de séance de l'Assemblée nationale (17e lég.)."""

import unicodedata
from collections import Counter
from datetime import date
from functools import lru_cache

from mcp.server.mcpserver import MCPServer

from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.mcp_serve import archives, guided_prompt, serve
from agora.contexts.assemblee import COLLECTION, SPEC
from agora.core.text import join_chunks

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
    rows = vs.select(COLLECTION, columns=["orateur"], limit=vs.count(COLLECTION))
    return dict(Counter(r["orateur"] for r in rows if r["orateur"]))


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
        date_min: date minimale incluse, format AAAA-MM-JJ. Seulement si l'utilisateur précise une période.
        date_max: date maximale incluse, format AAAA-MM-JJ. Seulement si l'utilisateur précise une période.
        limit: nombre d'extraits à retourner (1-20).
    """
    where = []
    if orateur:
        where.append(f"orateur = {vs.quote(orateur)}")
    if date_min:
        where.append(f"date_int >= {_date_int(date_min)}")
    if date_max:
        where.append(f"date_int <= {_date_int(date_max)}")
    hits = vs.search(COLLECTION, vs.embed([query])[0], " AND ".join(where) or None, limit=max(1, min(limit, 20)))
    return [_format(h, h["score"]) for h in hits]


@mcp.tool()
def get_contexte(seance_uid: str, ordre: int, avant: int = 3, apres: int = 3) -> list[dict]:
    """Retourne les interventions qui entourent un extrait (qui a répondu quoi), dans l'ordre de la séance.

    Args:
        seance_uid: identifiant de séance renvoyé par search_debats.
        ordre: position de l'extrait dans la séance, renvoyée par search_debats.
        avant: nombre d'interventions précédentes.
        apres: nombre d'interventions suivantes.
    """
    # L'ordre est la position du paragraphe dans la séance, pas un rang d'intervention :
    # on prend une fenêtre large puis on coupe.
    points = vs.select(
        COLLECTION,
        f"seance_uid = {vs.quote(seance_uid)} AND ordre BETWEEN {int(ordre) - 60} AND {int(ordre) + 60}",
        limit=500,
    )
    # Recolle les chunks d'une même intervention.
    by_ordre: dict[int, list[dict]] = {}
    for p in sorted(points, key=lambda p: (p["ordre"], p["chunk_index"])):
        by_ordre.setdefault(p["ordre"], []).append(p)
    rows = [{**chunks[0], "text": join_chunks([c["text"] for c in chunks])} for chunks in by_ordre.values()]
    idx = next((i for i, p in enumerate(rows) if p["ordre"] >= ordre), len(rows))
    return [_format(p) for p in rows[max(0, idx - avant) : idx + apres + 1]]


# Règles transmises à l'assistant de l'utilisateur par les prompts : c'est lui qui rédige la réponse.
RULES = [
    "Ne rapporte que ce qui figure dans les extraits renvoyés par les outils, jamais ce que tu crois savoir.",
    "Pour chaque position : l'orateur (et son groupe s'il est indiqué), la date et le lien de la séance.",
    "Distingue la citation, entre guillemets et mot pour mot du champ `texte`, du résumé.",
    "Reste neutre : rapporte les positions sans les juger, et ne prête à personne ce qu'un autre a dit.",
    "Si rien n'est trouvé, dis-le : ce n'est pas la preuve qu'un orateur n'a pas de position.",
    "Les archives s'arrêtent à la date indiquée : ne conclus pas au silence sur une période postérieure.",
]


@mcp.resource(
    "assemblee://archives",
    title="Archives de L'Hémicycle",
    description="Étendue des comptes rendus indexés, outils disponibles et exemples de questions.",
    mime_type="application/json",
)
def archives_assemblee() -> dict:
    return archives(SPEC)


@mcp.prompt(
    name="position-orateur",
    title="Position d'un orateur sur un sujet",
    description="Ce qu'un député ou un ministre a dit en séance sur un sujet, daté et sourcé.",
)
def position_orateur(orateur: str, sujet: str) -> str:
    return guided_prompt(
        SPEC,
        f"Qu'a dit {orateur} en séance publique sur le sujet suivant : « {sujet} » ?",
        [
            f"Appelle find_orateurs avec « {orateur} » pour obtenir son nom exact (sans civilité).",
            "Appelle search_debats avec ce sujet et le filtre orateur ; reformule et relance si c'est maigre.",
            "Si un extrait répond à quelqu'un, appelle get_contexte pour situer l'échange.",
            "Restitue ses positions dans l'ordre chronologique, avec une citation courte pour chacune.",
        ],
        RULES,
    )


@mcp.prompt(
    name="debat-sur-un-sujet",
    title="Le débat sur un sujet",
    description="Les positions défendues en séance sur un sujet, orateur par orateur, sur une période optionnelle.",
)
def debat_sur_un_sujet(sujet: str, date_min: str | None = None, date_max: str | None = None) -> str:
    period = " ".join(x for x in (date_min and f"à partir du {date_min}", date_max and f"jusqu'au {date_max}") if x)
    return guided_prompt(
        SPEC,
        f"Quelles positions ont été défendues en séance publique sur « {sujet} »{f' ({period})' if period else ''} ?",
        [
            "Appelle search_debats avec ce sujet, sans filtre orateur"
            + (f", avec date_min={date_min}" if date_min else "")
            + (f", avec date_max={date_max}" if date_max else "")
            + " ; relance avec deux ou trois reformulations pour couvrir les angles du débat.",
            "Regroupe les extraits par orateur et par groupe politique quand il est indiqué.",
            "Présente les positions en présence, puis les points d'accord et de désaccord qui ressortent des extraits.",
        ],
        RULES,
    )


@mcp.prompt(
    name="qui-a-repondu",
    title="Qui a répondu à qui",
    description="Retrouve une intervention et le fil de l'échange qui l'entoure dans la séance.",
)
def qui_a_repondu(orateur: str, sujet: str) -> str:
    return guided_prompt(
        SPEC,
        f"Retrouve l'intervention de {orateur} sur « {sujet} » et montre qui lui a répondu en séance.",
        [
            f"Appelle find_orateurs avec « {orateur} », puis search_debats avec le sujet et ce nom exact.",
            "Sur l'extrait le plus pertinent, appelle get_contexte avec son seance_uid et son ordre.",
            "Restitue l'échange dans l'ordre de la séance : qui parle, en une phrase chacun, avec la date et le lien.",
        ],
        RULES,
    )


def main() -> None:
    serve(mcp, default_port=8102)


if __name__ == "__main__":
    main()
