"""Contexte « cinéma » : ~35 000 synopsis Wikipédia, servis par le serveur MCP cinema."""

from agora.core.context import ContextSpec, DataSource, Identity

COLLECTION = "films"

SPEC = ContextSpec(
    id="cinema",
    identity=Identity(
        place="La Salle obscure",
        description=(
            "Synopsis de ~35 000 films issus de Wikipédia (en anglais) : retrouver un film à partir d'une "
            "intrigue, d'une ambiance ou d'un souvenir flou, et lire sa fiche. Chaque film renvoie vers sa page."
        ),
        corpus_label="35 000 films",
    ),
    server_module="agora.contexts.cinema.server",
    collections=(COLLECTION,),
    sources=(
        DataSource(
            name="Wikipédia en anglais, sections « Plot » des articles de films",
            url="https://en.wikipedia.org/",
            producer="Contributeurs de Wikipédia",
            license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        ),
        DataSource(
            name="Wikipedia Movie Plots with AI Plot Summaries (miroir Hugging Face)",
            url="https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries",
            producer="JustinR (collecte, Kaggle) ; Gabriel Tardochi (résumés DistilBART)",
            license="CC BY-SA 4.0",
            license_url="https://creativecommons.org/licenses/by-sa/4.0/",
        ),
    ),
    suggestions=(
        "Un film où un homme revit la même journée en boucle",
        "Des films de science-fiction réalisés par Ridley Scott",
        "Un thriller psychologique avec un narrateur qui perd la mémoire",
        "Un film d'animation japonais sur un esprit de la forêt",
    ),
    coverage_column="year",
    coverage_label="films sortis de {min} à {max}",
    tool_labels={"search_films": "Recherche dans les synopsis", "get_film": "Lecture de la fiche du film"},
)
