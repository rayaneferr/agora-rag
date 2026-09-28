"""Adaptateur entrant HTTP : sert l'interface et relaie le chat (SSE) vers l'agent du contexte choisi.

uv run agora            # http://127.0.0.1:8765 (ouvre le navigateur)
uv run agora --dev      # API seule, pour `npm run dev` dans web/
"""

import argparse
import asyncio
import json
import logging
import threading
import webbrowser
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agora.adapters.outbound import llm
from agora.adapters.outbound.mcp import McpGateway
from agora.adapters.outbound.vectorstore import ROOT, qdrant
from agora.contexts import CONTEXTS
from agora.core.agent import LLMError, Turn, run_turn

log = logging.getLogger("agora")
WEB_DIST = ROOT / "web" / "dist"


class State:
    gateways: dict[str, McpGateway] = {}
    index_status: str = "unknown"  # ready | downloading | error | unknown
    index_error: str | None = None


state = State()


def _prepare_index() -> None:
    """Restaure l'index (Hugging Face) si des collections manquent ; en tâche de fond."""
    from agora.adapters.outbound.snapshots import COLLECTIONS, ensure_index

    try:
        if all(qdrant().collection_exists(c) for c in COLLECTIONS):
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
        # Une passerelle par contexte : chaque agent ne voit que les outils de son domaine.
        for cid, spec in CONTEXTS.items():
            state.gateways[cid] = await stack.enter_async_context(McpGateway(spec))
            log.info("Contexte %s : outils %s", cid, ", ".join(state.gateways[cid].tool_names))
        yield


app = FastAPI(title="Agora", lifespan=lifespan)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    context: str
    provider: str
    model: str
    message: str = Field(min_length=1, max_length=8000)
    history: list[ChatMessage] = []


def _points(collection: str) -> int | None:
    try:
        return qdrant().count(collection, exact=False).count if qdrant().collection_exists(collection) else 0
    except Exception:
        return None  # Qdrant injoignable


@app.get("/api/health")
def health():
    return {"index": {"status": state.index_status, "error": state.index_error}}


@app.get("/api/contexts")
def get_contexts():
    return [
        {
            "id": cid,
            **asdict(spec.identity),
            "suggestions": list(spec.suggestions),
            "tools": [{"name": n, "label": spec.tool_labels.get(n, n)} for n in state.gateways[cid].tool_names]
            if cid in state.gateways
            else [],
            "points": sum(p or 0 for p in map(_points, spec.collections)),
        }
        for cid, spec in CONTEXTS.items()
    ]


@app.get("/api/providers")
def get_providers():
    return llm.list_providers()


@app.get("/api/models")
async def get_models(provider: str):
    try:
        return await llm.list_models(provider)
    except llm.ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@app.post("/api/chat")
async def chat(body: ChatRequest):
    spec = CONTEXTS.get(body.context)
    if spec is None or body.context not in state.gateways:
        raise HTTPException(status_code=404, detail=f"Contexte « {body.context} » inconnu.")
    try:
        model = llm.make_llm(body.provider, body.model)
    except llm.ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    turn = Turn(message=body.message, history=[m.model_dump() for m in body.history])

    async def events():
        try:
            async for event in run_turn(spec, model, state.gateways[body.context], turn):
                yield _sse(event)
        except LLMError as exc:
            yield _sse({"type": "error", "kind": exc.kind, "message": str(exc)})
        except asyncio.CancelledError:  # l'utilisateur a arrêté la génération
            raise
        except Exception as exc:
            log.exception("Erreur pendant le chat")
            yield _sse({"type": "error", "kind": "server", "message": str(exc)[:400]})

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
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
