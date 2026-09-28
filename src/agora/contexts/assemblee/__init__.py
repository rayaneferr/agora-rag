"""Contexte « Assemblée nationale » : comptes rendus des séances publiques (17e législature)."""

from agora.core.context import ContextSpec, DataSource, Identity

COLLECTION = "debats"

SPEC = ContextSpec(
    id="assemblee",
    identity=Identity(
        place="L'Hémicycle",
        description=(
            "Comptes rendus des séances publiques de l'Assemblée nationale depuis juillet 2024 : qui a dit quoi, "
            "quand, et sur quel texte. Chaque extrait renvoie vers le compte rendu de la séance."
        ),
        corpus_label="601 séances · 17e législature",
    ),
    server_module="agora.contexts.assemblee.server",
    collections=(COLLECTION,),
    sources=(
        DataSource(
            name="Comptes rendus des débats en séance publique, 17e législature (XML Syceron)",
            url="https://data.assemblee-nationale.fr/travaux-parlementaires/debats",
            producer="Assemblée nationale",
            license="Licence Ouverte / Open Licence (Etalab, octobre 2011)",
            license_url="https://data.assemblee-nationale.fr/licence-ouverte-open-licence",
        ),
    ),
    suggestions=(
        "Qu'a dit Éric Coquerel sur la dette publique ?",
        "Comment les députés ont-ils débattu de l'intelligence artificielle ?",
        "Quelles positions ont été défendues sur la protection des mineurs en ligne ?",
        "Que s'est-il dit sur la réforme des retraites en 2025 ?",
    ),
    coverage_column="date",
    coverage_label="séances du {min} au {max}",
    tool_labels={
        "find_orateurs": "Identification de l'orateur",
        "search_debats": "Recherche dans les comptes rendus",
        "get_contexte": "Lecture du déroulé de la séance",
    },
)
