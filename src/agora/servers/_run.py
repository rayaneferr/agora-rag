"""Point d'entrée commun aux serveurs MCP : stdio (lancé par un client) ou HTTP (service autonome)."""

import argparse
import os

from mcp.server.mcpserver import MCPServer

from agora.common import warm_up


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
    args = parser.parse_args()

    warm_up()
    if args.transport == "stdio":
        mcp.run("stdio")
    else:
        # Sans état : chaque requête est autonome, ce qui permet de scaler horizontalement derrière un proxy.
        mcp.run("streamable-http", host=args.host, port=args.port, stateless_http=True)
