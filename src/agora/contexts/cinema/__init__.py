"""Contexte « cinéma » : ~35 000 synopsis Wikipédia, servis par le serveur MCP cinema."""

from typing import Any

from agora.core.context import ContextSpec, Identity, Source

COLLECTION = "films"


def to_sources(tool: str, payload: Any) -> list[Source]:
    items = payload if isinstance(payload, list) else [payload]
    return [
        Source(
            kind="film",
            title=it.get("title") or "?",
            subtitle=" · ".join(str(x) for x in (it.get("year"), it.get("director")) if x),
            url=it.get("wiki_url"),
            excerpt=(it.get("summary") or it.get("matching_excerpt") or it.get("plot") or "")[:280],
            score=it.get("score"),
        )
        for it in items
        if isinstance(it, dict) and "error" not in it
    ]


SPEC = ContextSpec(
    id="cinema",
    identity=Identity(
        place="La Salle obscure",
        agent="Lumière",
        tagline="Raconte une scène, je retrouve le film.",
        description=(
            "Décris une intrigue, une ambiance ou un souvenir flou : Lumière fouille 35 000 synopsis "
            "Wikipédia et te propose les films qui correspondent, avec leur fiche."
        ),
        theme="salle",
        emblem="clap",
        corpus_label="35 000 films",
    ),
    system_prompt="""Tu es Lumière, l'ouvreuse passionnée de « La Salle obscure ». Tu aides à retrouver et à
découvrir des films grâce à une base de ~35 000 synopsis Wikipédia (en anglais).
- search_films pour chercher par intrigue, thème ou ambiance ; formule la requête en anglais, c'est la langue
  des synopsis. Filtres possibles : genre, réalisateur, années.
- get_film pour lire le synopsis complet d'un film avant d'en parler en détail.
- Cite chaque film avec son titre et son année ; un ton chaleureux de cinéphile, sans divulgâcher la fin
  sauf si on te le demande.""",
    server_module="agora.contexts.cinema.server",
    collections=(COLLECTION,),
    suggestions=(
        "Un film où un homme revit la même journée en boucle",
        "Des films de science-fiction réalisés par Ridley Scott",
        "Un thriller psychologique avec un narrateur qui perd la mémoire",
        "Un film d'animation japonais sur un esprit de la forêt",
    ),
    tool_labels={"search_films": "Recherche dans les synopsis", "get_film": "Lecture de la fiche du film"},
    to_sources=to_sources,
)
