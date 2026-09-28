"""Adaptateur entrant « MCP en HTTP » : les serveurs de tous les contextes, sur un seul port.

uv run agora-mcp-public                      # http://127.0.0.1:8100/cinema/mcp, /assemblee/mcp, /health
uv run agora-mcp-public --host 0.0.0.0 --allow-remote   # exposé au-delà de la machine (hébergement)

Pour les clients qui parlent HTTP plutôt que stdio, et pour héberger le service : un seul processus pour tous les
contextes, donc bge-m3 (~2,3 Go) n'est chargé qu'une fois et un seul port suffit. Les serveurs sont sans état et en
lecture seule ; faute d'authentification (le corpus est public), une exposition au-delà de la machine repose sur
des garde-fous : hôtes autorisés, taille des requêtes, débit par IP.
"""

import argparse
import importlib
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import AsyncExitStack, asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.mcp_serve import coverage, is_loopback
from agora.contexts import CONTEXTS

log = logging.getLogger("agora.mcp")
# Une requête MCP légitime (appel d'outil, prompt) tient en quelques Ko ; au-delà, on refuse avant de lire.
MAX_BODY_BYTES = 64 * 1024
LOOPBACK_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
LOOPBACK_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _env_list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def client_ip(scope: dict, forwarded_hops: int) -> str:
    """IP du client. Derrière N proxys de confiance, c'est la N-ième entrée de X-Forwarded-For en partant de la fin :
    les entrées plus à gauche sont fournies par le client lui-même et ne prouvent rien."""
    peer = (scope.get("client") or ("?", 0))[0]
    if forwarded_hops <= 0:
        return peer
    header = dict(scope.get("headers") or []).get(b"x-forwarded-for", b"").decode()
    chain = [x.strip() for x in header.split(",") if x.strip()]
    return chain[-forwarded_hops] if len(chain) >= forwarded_hops else peer


class RateLimit:
    """Limite de débit par IP (fenêtre glissante d'une minute), en mémoire : suffisant pour un seul processus."""

    def __init__(self, app, per_minute: int, forwarded_hops: int = 0, exempt: tuple[str, ...] = ()):
        self.app = app
        self.per_minute = per_minute
        self.forwarded_hops = forwarded_hops
        self.exempt = exempt
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self.per_minute <= 0 or scope["path"] in self.exempt:
            return await self.app(scope, receive, send)
        now = time.monotonic()
        window = self.hits[client_ip(scope, self.forwarded_hops)]
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self.per_minute:
            retry = int(60 - (now - window[0])) + 1
            response = JSONResponse(
                {"error": f"Trop de requêtes : {self.per_minute} par minute au plus."},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
            return await response(scope, receive, send)
        window.append(now)
        if len(self.hits) > 10_000:  # borne la mémoire : on oublie les IP inactives
            for ip in [ip for ip, w in self.hits.items() if not w or now - w[-1] >= 60]:
                del self.hits[ip]
        return await self.app(scope, receive, send)


def _server(module: str) -> MCPServer:
    return importlib.import_module(module).mcp


def create_app(
    allowed_hosts: list[str] | None = None,
    allowed_origins: list[str] | None = None,
    rate_limit: int = 60,
    forwarded_hops: int = 0,
    warm_up=vs.warm_up,
    embedder_loaded=vs.embedder_loaded,
):
    """Une app ASGI : /<contexte>/mcp pour chaque contexte du registre, / et /health pour l'état du service."""
    hosts = list(allowed_hosts or [])
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=LOOPBACK_HOSTS + hosts,
        allowed_origins=LOOPBACK_ORIGINS + (allowed_origins or [f"https://{h}" for h in hosts]),
    )
    servers = {cid: _server(spec.server_module) for cid, spec in CONTEXTS.items()}
    mounts = [
        Mount(
            f"/{cid}",
            app=server.streamable_http_app(
                streamable_http_path="/mcp",
                stateless_http=True,  # chaque requête est autonome : pas de session à garder ni à faire fuiter
                json_response=True,
                max_request_body_size=MAX_BODY_BYTES,
                transport_security=security,
            ),
        )
        for cid, server in servers.items()
    ]

    def health(request: Request) -> JSONResponse:
        contexts = {}
        for cid, spec in CONTEXTS.items():
            try:
                indexed = sum(vs.count(c) for c in spec.collections)
            except Exception:
                indexed = 0
            contexts[cid] = {
                "lieu": spec.identity.place,
                "endpoint": f"/{cid}/mcp",
                "etendue": coverage(spec),
                "extraits_indexes": indexed,
            }
        # 503 tant que le service ne peut pas répondre vite : index absent, ou bge-m3 encore en chargement.
        if not all(c["extraits_indexes"] > 0 for c in contexts.values()):
            status = "degraded"
        else:
            status = "ok" if embedder_loaded() else "starting"
        return JSONResponse(
            {
                "name": "agora-mcp",
                "status": status,
                "embedder": "ready" if embedder_loaded() else "loading",
                "transport": "streamable-http",
                "description": "Serveurs MCP d'Agora : RAG sur des synopsis de films et les débats de l'Assemblée "
                "nationale. Public, en lecture seule, sans authentification.",
                "contexts": contexts,
            },
            status_code=200 if status == "ok" else 503,
        )

    @asynccontextmanager
    async def lifespan(app):
        # Starlette ne lance pas le cycle de vie des apps montées : on démarre nous-mêmes chaque gestionnaire.
        warm_up()
        async with AsyncExitStack() as stack:
            for server in servers.values():
                await stack.enter_async_context(server.session_manager.run())
            yield

    app = Starlette(routes=[Route("/", health), Route("/health", health), *mounts], lifespan=lifespan)
    return RateLimit(app, rate_limit, forwarded_hops, exempt=("/", "/health"))


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Agora — serveurs MCP publics (tous les contextes, un seul port)")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8100")))
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Autorise une adresse d'écoute non locale (les outils n'ont aucune authentification)",
    )
    args = parser.parse_args()
    if not is_loopback(args.host) and not args.allow_remote:
        raise SystemExit(
            f"Refus d'écouter sur {args.host} : les outils MCP n'ont pas d'authentification. "
            "Garde 127.0.0.1, ou passe --allow-remote si c'est voulu."
        )

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    app = create_app(
        allowed_hosts=_env_list("MCP_ALLOWED_HOSTS"),
        allowed_origins=_env_list("MCP_ALLOWED_ORIGINS") or None,
        rate_limit=int(os.getenv("MCP_RATE_LIMIT", "60")),
        forwarded_hops=int(os.getenv("MCP_FORWARDED_HOPS", "0")),
    )
    log.info("Serveurs MCP : %s", ", ".join(f"http://{args.host}:{args.port}/{cid}/mcp" for cid in CONTEXTS))
    # Journal d'accès désactivé : il n'apprendrait rien (les questions sont dans le corps des requêtes, jamais
    # journalisé) mais conserverait les IP des visiteurs.
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
