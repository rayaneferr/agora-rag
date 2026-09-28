"""API web locale : sert l'interface et relaie le chat (SSE) entre le navigateur, le LLM et les serveurs MCP.

uv run agora            # http://127.0.0.1:8765 (ouvre le navigateur)
uv run agora --dev      # API seule, pour `npm run dev` dans web/

La clé API arrive avec chaque requête, n'est ni stockée ni journalisée côté serveur.
"""

import argparse
import asyncio
import json
import logging
import threading
import webbrowser
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from mcp.client.session_group import ClientSessionGroup
from pydantic import BaseModel, Field

from agora import providers
from agora.agent import LLMError, Turn, connect_servers, demo_stream, litellm_stream, run_turn, scrub
from agora.common import COLLECTION_DEBATS, COLLECTION_FILMS, ROOT, qdrant

log = logging.getLogger("agora")
WEB_DIST = ROOT / "web" / "dist"


class State:
    group: ClientSessionGroup | None = None
    tool_servers: dict[str, str] = {}
    index_status: str = "unknown"  # ready | downloading | error | unknown
    index_error: str | None = None


state = State()


def _prepare_index() -> None:
    """Restaure l'index (Hugging Face) si des collections manquent ; en tâche de fond."""
    from agora.snapshots import COLLECTIONS, ensure_index

    try:
        client = qdrant()
        if all(client.collection_exists(c) for c in COLLECTIONS):
            state.index_status = "ready"
            return
        state.index_status = "downloading"
        ensure_index()
        state.index_status = "ready"
    except Exception as exc:
        state.index_status, state.index_error = "error", str(exc)[:300]
        log.warning("Index indisponible : %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_prepare_index, daemon=True).start()
    async with AsyncExitStack() as stack:
        state.group = await stack.enter_async_context(ClientSessionGroup())
        state.tool_servers = await connect_servers(state.group)
        log.info("Outils MCP : %s", ", ".join(state.tool_servers))
        yield


app = FastAPI(title="Agora", lifespan=lifespan)


# --- Schémas -----------------------------------------------------------------------------------


class KeyCheck(BaseModel):
    provider: str
    api_key: str = ""


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    provider: str
    model: str
    api_key: str = ""
    message: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = []


# --- Routes ------------------------------------------------------------------------------------


@app.get("/api/health")
def health():
    counts = {}
    for name in (COLLECTION_FILMS, COLLECTION_DEBATS):
        try:
            counts[name] = qdrant().count(name, exact=False).count if qdrant().collection_exists(name) else 0
        except Exception:
            counts[name] = None  # Qdrant injoignable
    return {
        "index": {"status": state.index_status, "error": state.index_error, "points": counts},
        "tools": [{"name": n, "server": s} for n, s in state.tool_servers.items()],
    }


@app.get("/api/providers")
def get_providers():
    return providers.list_providers()


@app.post("/api/models")
async def get_models(body: KeyCheck):
    try:
        return await providers.list_models(body.provider, body.api_key)
    except providers.ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatRequest):
    if body.provider == "demo" and providers.demo_enabled():
        llm = demo_stream
    elif body.provider == "openai":
        llm = litellm_stream
    else:
        raise HTTPException(status_code=400, detail=f"Provider « {body.provider} » pas encore disponible.")
    turn = Turn(
        model=body.model,
        api_key=body.api_key or None,
        history=[m.model_dump() for m in body.history],
        message=body.message,
    )

    async def events():
        try:
            async for event in run_turn(state.group, turn, state.tool_servers, llm=llm):
                yield _sse(event)
        except LLMError as exc:
            yield _sse({"type": "error", "kind": exc.kind, "message": str(exc)})
        except asyncio.CancelledError:  # l'utilisateur a arrêté la génération
            raise
        except Exception as exc:
            log.exception("Erreur pendant le chat")
            yield _sse({"type": "error", "kind": "server", "message": scrub(str(exc), turn.api_key)[:400]})

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Agora — interface locale")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dev", action="store_true", help="API seule (front servi par Vite)")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    if not args.dev and not WEB_DIST.exists():
        raise SystemExit("Interface non construite : lance `npm install && npm run build` dans web/ (ou --dev).")
    url = f"http://127.0.0.1:{args.port}"
    if not args.dev and not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    # 127.0.0.1 uniquement : l'app est locale, la clé ne doit pas transiter sur le réseau local.
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
