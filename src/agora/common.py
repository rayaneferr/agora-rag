"""Briques partagées : config, modèle d'embeddings, client Qdrant."""

import os
import threading
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

COLLECTION_FILMS = "films"
COLLECTION_DEBATS = "debats"


_embedder_lock = threading.Lock()


@lru_cache
def _load_embedder():
    # Import tardif : sentence-transformers + torch mettent plusieurs secondes à charger,
    # on ne veut pas bloquer le handshake MCP au démarrage du serveur.
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(EMBED_MODEL, device=device)
    if device == "mps":
        model.half()
    return model


def embedder():
    with _embedder_lock:  # warm_up() et un premier appel d'outil peuvent arriver en même temps
        return _load_embedder()


def warm_up() -> None:
    """Charge le modèle en tâche de fond : le handshake MCP n'attend pas, et le premier appel d'outil non plus."""
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    threading.Thread(target=embedder, daemon=True).start()


def embed(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    vectors = embedder().encode(
        texts, batch_size=batch_size, normalize_embeddings=True, show_progress_bar=len(texts) > batch_size
    )
    return vectors.tolist()


def embedding_dim() -> int:
    return embedder().get_embedding_dimension()


@lru_cache
def qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


CHUNK_OVERLAP = 200


def join_chunks(chunks: list[str], overlap: int = CHUNK_OVERLAP) -> str:
    """Inverse de chunk_text : recolle les chunks sans dupliquer le recouvrement des fenêtres glissantes."""
    if not chunks:
        return ""
    out = chunks[0]
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        if len(prev) >= overlap and cur[:overlap] == prev[-overlap:]:
            out += cur[overlap:]  # fenêtre glissante : suite directe du même paragraphe
        else:
            out += "\n" + cur
    return out


def chunk_text(text: str, max_chars: int = 1500, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Découpe sur les paragraphes puis, si besoin, en fenêtres glissantes."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for para in (p.strip() for p in text.split("\n") if p.strip()):
        if len(current) + len(para) + 1 <= max_chars:
            current = f"{current}\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
        while len(para) > max_chars:
            chunks.append(para[:max_chars])
            para = para[max_chars - overlap :]
        current = para
    if current:
        chunks.append(current)
    return chunks
