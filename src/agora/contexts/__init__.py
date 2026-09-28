"""Registre des contextes délimités. Ajouter un contexte = l'importer ici."""

from agora.contexts.assemblee import SPEC as ASSEMBLEE
from agora.contexts.cinema import SPEC as CINEMA
from agora.core.context import ContextSpec

CONTEXTS: dict[str, ContextSpec] = {spec.id: spec for spec in (CINEMA, ASSEMBLEE)}
