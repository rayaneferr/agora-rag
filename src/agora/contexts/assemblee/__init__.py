"""Contexte « Assemblée nationale » : comptes rendus des séances publiques (17e législature)."""

from typing import Any

from agora.core.context import ContextSpec, Identity, Source

COLLECTION = "debats"


def to_sources(tool: str, payload: Any) -> list[Source]:
    items = payload if isinstance(payload, list) else [payload]
    sources = []
    for it in items:
        if not isinstance(it, dict) or "error" in it or "texte" not in it:
            continue  # find_orateurs renvoie des noms, pas des extraits citables
        who = it.get("orateur", "") + (f" ({it['groupe']})" if it.get("groupe") else "")
        sources.append(
            Source(
                kind="seance",
                title=who,
                subtitle=" · ".join(x for x in (it.get("date"), it.get("section"), it.get("sujet")) if x),
                url=it.get("url"),
                excerpt=(it.get("texte") or "")[:280],
                score=it.get("score"),
            )
        )
    return sources


SPEC = ContextSpec(
    id="assemblee",
    identity=Identity(
        place="L'Hémicycle",
        agent="L'Huissier",
        tagline="Ce qui s'est dit en séance, sources à l'appui.",
        description=(
            "Interroge les comptes rendus des séances publiques de l'Assemblée nationale depuis juillet 2024 : "
            "qui a dit quoi, quand, et sur quel texte. Chaque réponse renvoie vers la séance."
        ),
        theme="hemicycle",
        emblem="hemicycle",
        corpus_label="601 séances · 17e législature",
    ),
    system_prompt="""Tu es L'Huissier de « L'Hémicycle ». Tu connais les comptes rendus des séances publiques de
l'Assemblée nationale (17e législature, depuis juillet 2024) et tu rapportes fidèlement ce qui s'y est dit.
- Pour une question sur une personne, trouve d'abord son nom exact avec find_orateurs, puis utilise-le
  comme filtre orateur de search_debats (sans civilité).
- search_debats pour chercher par sujet ; get_contexte pour voir qui a répondu quoi autour d'un extrait.
- Cite toujours l'orateur, la date et le lien de la séance. Reste neutre : rapporte les positions, ne les
  juge pas, et distingue bien ce que dit chaque orateur.""",
    server_module="agora.contexts.assemblee.server",
    collections=(COLLECTION,),
    suggestions=(
        "Qu'a dit Éric Coquerel sur la dette publique ?",
        "Comment les députés ont-ils débattu de l'intelligence artificielle ?",
        "Quelles positions ont été défendues sur la protection des mineurs en ligne ?",
        "Que s'est-il dit sur la réforme des retraites en 2025 ?",
    ),
    tool_labels={
        "find_orateurs": "Identification de l'orateur",
        "search_debats": "Recherche dans les comptes rendus",
        "get_contexte": "Lecture du déroulé de la séance",
    },
    to_sources=to_sources,
)
