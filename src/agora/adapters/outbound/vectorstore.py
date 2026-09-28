"""Adaptateur sortant « recherche vectorielle » : configuration, modèle d'embeddings (bge-m3), client Qdrant."""

import os
import threading
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient

ROOT = Path(__file__).resolve().parents[4]  # racine du dépôt
DATA_DIR = ROOT / "data"

load_dotenv(ROOT / ".env")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")

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
