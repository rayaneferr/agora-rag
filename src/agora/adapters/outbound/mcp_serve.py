"""Ce que les serveurs MCP ont en commun : point d'entrée (stdio ou HTTP), description des archives, prompts guidés."""

import argparse
import ipaddress
import os
from dataclasses import asdict

from mcp.server.mcpserver import MCPServer

from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.vectorstore import warm_up
from agora.core.context import ContextSpec


def coverage(spec: ContextSpec) -> str | None:
    """Étendue réelle des archives, lue dans l'index : le client MCP doit savoir où elles s'arrêtent."""
    if not spec.coverage_column:
        return None
    try:
        return spec.coverage_text(vs.bounds(spec.collections[0], spec.coverage_column))
    except Exception:
        return None  # index absent ou illisible : on décrit le reste sans l'étendue


def archives(spec: ContextSpec) -> dict:
    """Contenu de la resource `<contexte>://archives` : ce que couvre la base, d'où elle vient, comment l'interroger.

    La provenance et la licence voyagent avec les données : un client qui réutilise les extraits sait qui citer.
    """
    return {
        "lieu": spec.identity.place,
        "description": spec.identity.description,
        "corpus": spec.identity.corpus_label,
        "etendue": coverage(spec),
        "extraits_indexes": sum(vs.count(c) for c in spec.collections),
        "outils": spec.tool_labels,
        "exemples": list(spec.suggestions),
        "sources": [asdict(source) for source in spec.sources],
    }


def guided_prompt(spec: ContextSpec, task: str, steps: list[str], rules: list[str]) -> str:
    """Prompt MCP prêt à l'emploi : la demande, l'étendue des archives, la marche à suivre et les règles.

    Il est lu par l'assistant de l'utilisateur (Claude, ChatGPT…) : on y rappelle les exigences de sourçage, car
    c'est le seul moyen de les transmettre à un modèle qu'on ne contrôle pas.
    """
    scope = spec.identity.corpus_label + (f", {cov}" if (cov := coverage(spec)) else "")
    lines = [task, "", f"Archives interrogées : {scope}.", "", "Marche à suivre :"]
    lines += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
    lines += ["", "Règles :"] + [f"- {rule}" for rule in rules]
    return "\n".join(lines)


def is_loopback(host: str) -> bool:
    if host in ("localhost", "ip6-localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def serve(mcp: MCPServer, default_port: int) -> None:
    parser = argparse.ArgumentParser(description=f"Serveur MCP « {mcp.name} »")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="stdio : lancé en sous-processus par le client ; http : service streamable-http sur /mcp",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Autorise une adresse d'écoute non locale (les outils n'ont aucune authentification)",
    )
    args = parser.parse_args()
    if args.transport == "http" and not is_loopback(args.host) and not args.allow_remote:
        raise SystemExit(
            f"Refus d'écouter sur {args.host} : les outils MCP n'ont pas d'authentification. "
            "Garde 127.0.0.1, ou passe --allow-remote si c'est voulu."
        )

    warm_up()
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        # Sans état : chaque requête est autonome, ce qui permet de scaler horizontalement derrière un proxy.
        mcp.run("streamable-http", host=args.host, port=args.port, stateless_http=True)
