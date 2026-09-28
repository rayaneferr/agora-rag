"""Un contexte délimité = une base indexée + un serveur MCP + une identité (persona, thème, prompts).

Le cœur ne connaît les contextes qu'à travers ce contrat : ajouter un domaine (sport, droit…) revient à
créer un dossier dans agora/contexts/ qui expose un ContextSpec, sans toucher au cœur ni à l'interface.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Source:
    """Une référence citable, affichée comme carte cliquable dans l'interface."""

    kind: str  # identifiant libre propre au contexte : "film", "seance"…
    title: str
    subtitle: str
    url: str | None
    excerpt: str
    score: float | None = None


@dataclass(frozen=True)
class Identity:
    """Ce que l'interface affiche : nom du lieu, de l'agent, accroche, thème visuel."""

    place: str  # nom du lieu : « La Salle obscure »
    agent: str  # nom de l'agent : « Lumière »
    tagline: str
    description: str
    theme: str  # clé du thème CSS côté front
    emblem: str  # clé de l'emblème SVG côté front
    corpus_label: str  # « 35 000 films », « 601 séances »


@dataclass(frozen=True)
class ContextSpec:
    id: str
    identity: Identity
    system_prompt: str
    server_module: str  # module Python du serveur MCP (lancé en stdio)
    collections: tuple[str, ...]  # tables de la base indexée
    suggestions: tuple[str, ...]
    tool_labels: dict[str, str] = field(default_factory=dict)  # nom d'outil → libellé lisible
    # Colonne dont les bornes (min, max) décrivent l'étendue des archives, et le gabarit qui les affiche.
    # Les archives ont une date de fin : l'interface et le prompt système doivent la connaître.
    coverage_column: str | None = None
    coverage_label: str = "de {min} à {max}"
    # Transforme le résultat brut d'un outil MCP en sources citables.
    to_sources: Callable[[str, Any], list[Source]] = lambda tool, payload: []
