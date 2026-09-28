"""Ports : ce dont le cœur a besoin, sans savoir qui le fournit (Ollama, démo, MCP stdio ou HTTP…)."""

from collections.abc import AsyncIterator
from typing import Any, Protocol


class LLMPort(Protocol):
    """Un appel au modèle, en streaming.

    Émet {"token": str} au fil de l'eau, puis un dernier
    {"final": message_openai, "usage": {"prompt_tokens", "completion_tokens"} | None, "cost": float}.
    """

    def __call__(self, messages: list[dict], tools: list[dict]) -> AsyncIterator[dict]: ...


class ToolGateway(Protocol):
    """Les outils d'un contexte, quel que soit le transport (MCP stdio, HTTP, en mémoire)."""

    def tool_schemas(self) -> list[dict]:
        """Outils au format « function calling » OpenAI."""
        ...

    async def call(self, name: str, args: dict) -> tuple[bool, Any]:
        """Exécute un outil ; renvoie (succès, contenu décodé)."""
        ...
