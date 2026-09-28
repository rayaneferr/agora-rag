"""Adaptateur entrant HTTP : sert l'interface et relaie le chat (SSE) vers l'agent du contexte choisi.

uv run agora            # http://127.0.0.1:8765 (ouvre le navigateur)
uv run agora --dev      # API seule, pour `npm run dev` dans web/
"""

import argparse
import asyncio
import contextlib
import json
import logging
import threading
import webbrowser
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agora.adapters.outbound import llm
from agora.adapters.outbound import vectorstore as vs
from agora.adapters.outbound.mcp import McpGateway
from agora.contexts import CONTEXTS
from agora.core.agent import LLMError, Turn, run_turn
from agora.core.context import ContextSpec

log = logging.getLogger("agora")
WEB_DIST = vs.ROOT / "web" / "dist"
# L'application n'écoute que sur la boucle locale ; on refuse aussi les requêtes dont l'en-tête Host
# ne la désigne pas (DNS rebinding : un site tiers ne doit pas pouvoir piloter l'agent).
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


class Download:
    """Progression d'un téléchargement de premier lancement, lue par /api/health."""

    def __init__(self):
        self.status = "unknown"  # ready | downloading | error | unknown
        self.error: str | None = None
        self.files: list = []
        self.progress = None  # callable → (done, total)

    def snapshot(self) -> dict:
        done = total = None
        if self.status == "downloading" and self.files and self.progress:
            with contextlib.suppress(OSError):
                done, total = self.progress(self.files)
        return {"status": self.status, "error": self.error, "done_bytes": done, "total_bytes": total}


class State:
    gateways: dict[str, McpGateway] = {}
    index = Download()
    embedder = Download()
    coverage: dict[str, str] = {}


state = State()


def _prepare() -> None:
    """Premier lancement : index (Hugging Face) puis modèle d'embeddings, en tâche de fond, état visible."""
    from agora.adapters.outbound import index_hub as hub

    try:
        if all(vs.has_table(c) for c in hub.COLLECTIONS):
            state.index.status = "ready"
        else:
            state.index.status = "downloading"
            progress: dict = {}
            state.index.files = progress.setdefault("files", [])
            state.index.progress = lambda files: hub.download_progress(vs.DB_DIR.parent, files)
            hub.ensure_index(progress)
            state.index.files = progress["files"]
            state.index.status = "ready"
    except Exception as exc:
        state.index.status, state.index.error = "error", str(exc)[:300]
        log.warning("Index indisponible : %s", exc)

    try:
        if hub.embedder_ready():
            state.embedder.status = "ready"
        else:
            state.embedder.status = "downloading"
            state.embedder.files = hub.embedder_files()
            state.embedder.progress = hub.embedder_progress
            hub.ensure_embedder()
            state.embedder.status = "ready"
    except Exception as exc:
        state.embedder.status, state.embedder.error = "error", str(exc)[:300]
        log.warning("Modèle d'embeddings indisponible : %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=_prepare, daemon=True).start()
    async with AsyncExitStack() as stack:
        # Une passerelle par contexte : chaque agent ne voit que les outils de son domaine.
        for cid, spec in CONTEXTS.items():
            state.gateways[cid] = await stack.enter_async_context(McpGateway(spec))
            log.info("Contexte %s : outils %s", cid, ", ".join(state.gateways[cid].tool_names))
        yield


app = FastAPI(title="Agora", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)


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
        return vs.count(collection)
    except Exception:
        return None  # table en cours de téléchargement


def coverage(spec: ContextSpec) -> str | None:
    """Étendue des archives d'un contexte (« séances du 18 juillet 2024 au 26 septembre 2026 »), mise en cache."""
    if spec.id in state.coverage or not spec.coverage_column:
        return state.coverage.get(spec.id)
    try:
        b = vs.bounds(spec.collections[0], spec.coverage_column)
    except Exception:
        return None
    text = spec.coverage_text(b)
    if text is not None:
        state.coverage[spec.id] = text
    return text


@app.get("/api/health")
def health():
    return {"index": state.index.snapshot(), "embedder": state.embedder.snapshot()}


@app.get("/api/contexts")
def get_contexts():
    return [
        {
            "id": cid,
            **asdict(spec.identity),
            "coverage": coverage(spec),
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
    if state.index.status != "ready":
        raise HTTPException(status_code=503, detail="Les archives ne sont pas encore prêtes.")
    try:
        model = llm.make_llm(body.provider, body.model)
    except llm.ProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    turn = Turn(message=body.message, history=[m.model_dump() for m in body.history])

    async def events():
        try:
            async for event in run_turn(spec, model, state.gateways[body.context], turn, coverage(spec)):
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
