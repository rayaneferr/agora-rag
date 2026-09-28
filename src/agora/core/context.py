"""Un contexte délimité = une base indexée + un serveur MCP + une description (archives, provenance, licence).

Le reste du code ne connaît les contextes qu'à travers ce contrat : ajouter un domaine (sport, droit…) revient
à créer un dossier dans agora/contexts/ qui expose un ContextSpec, et à l'inscrire dans le registre.
"""

from dataclasses import dataclass, field
from datetime import date

MOIS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def _fr(value) -> str:
    """Une borne lisible : « 18 juillet 2024 » pour une date ISO, la valeur brute sinon."""
    if isinstance(value, str) and len(value) == 10 and value[4] == "-":
        try:
            d = date.fromisoformat(value)
            return f"{d.day} {MOIS[d.month - 1]} {d.year}"
        except ValueError:
            return value
    return str(value)


@dataclass(frozen=True)
class Identity:
    """Comment le contexte se présente au client MCP."""

    place: str  # nom du contexte : « La Salle obscure »
    description: str
    corpus_label: str  # « 35 000 films », « 601 séances »


@dataclass(frozen=True)
class DataSource:
    """Provenance d'un corpus et licence sous laquelle il est réutilisé : ce qu'il faut citer pour s'y conformer."""

    name: str
    url: str
    producer: str  # à qui revient la paternité de l'information
    license: str
    license_url: str


@dataclass(frozen=True)
class ContextSpec:
    id: str
    identity: Identity
    server_module: str  # module Python du serveur MCP
    collections: tuple[str, ...]  # tables de la base indexée
    sources: tuple[DataSource, ...]
    suggestions: tuple[str, ...]
    tool_labels: dict[str, str] = field(default_factory=dict)  # nom d'outil → libellé lisible
    # Colonne dont les bornes (min, max) décrivent l'étendue des archives, et le gabarit qui les affiche.
    # Les archives ont une date de fin : le client MCP doit la connaître pour ne pas conclure au silence.
    coverage_column: str | None = None
    coverage_label: str = "de {min} à {max}"

    def coverage_text(self, bounds: tuple | None) -> str | None:
        """Étendue lisible (« séances du 18 juillet 2024 au 26 septembre 2026 ») à partir des bornes de l'index."""
        if bounds is None:
            return None
        return self.coverage_label.format(min=_fr(bounds[0]), max=_fr(bounds[1]))
