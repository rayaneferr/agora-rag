"""Point d'entrée commun aux serveurs MCP : stdio (lancé par un client) ou HTTP (service autonome)."""

import argparse
import ipaddress
import os

from mcp.server.mcpserver import MCPServer

from agora.adapters.outbound.vectorstore import warm_up


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
