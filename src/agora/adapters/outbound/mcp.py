"""Adaptateur sortant « outils » : passerelle MCP vers le serveur d'un contexte (implémente ToolGateway)."""

import contextlib
import json
import sys
from typing import Any

from mcp.client.session_group import ClientSessionGroup, StreamableHttpParameters
from mcp.client.stdio import StdioServerParameters

from agora.adapters.outbound.vectorstore import ROOT
from agora.core.context import ContextSpec


def decode(result) -> Any:
    """Contenu d'un résultat MCP : structuré si possible, sinon JSON dans le texte, sinon texte brut."""
    if result.structured_content is not None:
        return result.structured_content.get("result", result.structured_content)
    text = "\n".join(getattr(c, "text", "") for c in result.content)
    with contextlib.suppress(json.JSONDecodeError):
        return json.loads(text)
    return text


class McpGateway:
    """Une session MCP vers le serveur d'un seul contexte : l'agent ne voit que les outils de son domaine."""

    def __init__(self, context: ContextSpec, url: str | None = None):
        self.context = context
        self.url = url
        self._group = ClientSessionGroup()

    async def __aenter__(self) -> "McpGateway":
        await self._group.__aenter__()
        if self.url:
            params = StreamableHttpParameters(url=self.url)
        else:
            params = StdioServerParameters(
                command=sys.executable, args=["-m", self.context.server_module], cwd=str(ROOT)
            )
        await self._group.connect_to_server(params)
        return self

    async def __aexit__(self, *exc) -> None:
        await self._group.__aexit__(*exc)

    @property
    def tool_names(self) -> list[str]:
        return list(self._group.tools)

    def tool_schemas(self) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {"name": n, "description": t.description or "", "parameters": t.input_schema},
            }
            for n, t in self._group.tools.items()
        ]

    async def call(self, name: str, args: dict) -> tuple[bool, Any]:
        result = await self._group.call_tool(name, args)
        return not result.is_error, decode(result)
