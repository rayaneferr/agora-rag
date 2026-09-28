"""Adaptateur sortant « recherche vectorielle » : modèle d'embeddings (bge-m3) et base LanceDB embarquée.

LanceDB est une bibliothèque, pas un serveur : l'index est un dossier (`data/lancedb/` par défaut, ou
`$AGORA_HOME/lancedb`), ouvert directement par le processus. Ni Docker, ni VM, ni service à lancer.
"""

import os
import threading
from functools import lru_cache
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[4]  # racine du dépôt (web/dist, .env)

load_dotenv(ROOT / ".env")

# Où vivent les données (index, fichiers sources téléchargés) : par défaut à côté du code.
DATA_DIR = Path(os.getenv("AGORA_HOME", ROOT / "data")).expanduser()
DB_DIR = DATA_DIR / "lancedb"  # une table = un dossier <nom>.lance
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
# Révision (commit) du modèle : les poids PyTorch sont du pickle, on ne charge que ceux qu'on a validés.
EMBED_REVISION = os.getenv("EMBED_REVISION", "5617a9f61b028005a4858fdac845db406aefb181")

_embedder_lock = threading.Lock()


@lru_cache
def _load_embedder():
    # Import tardif : sentence-transformers + torch mettent plusieurs secondes à charger,
    # on ne veut pas bloquer le handshake MCP au démarrage du serveur.
    import torch
    from sentence_transformers import SentenceTransformer

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    kwargs = {"device": device, "revision": EMBED_REVISION}
    try:  # modèle déjà en cache : aucun appel au Hub
        model = SentenceTransformer(EMBED_MODEL, local_files_only=True, **kwargs)
    except OSError:  # premier lancement : téléchargement (~2,3 Go), une seule fois
        model = SentenceTransformer(EMBED_MODEL, **kwargs)
    if device == "mps":
        model.half()
    return model


def embedder():
    with _embedder_lock:  # warm_up() et un premier appel d'outil peuvent arriver en même temps
        return _load_embedder()


def embedder_loaded() -> bool:
    """Le modèle est-il en mémoire ? Tant que non, le premier appel d'outil attend son chargement (~20 s)."""
    return _load_embedder.cache_info().currsize > 0


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
def db():
    import lancedb

    return lancedb.connect(DB_DIR)


def has_table(name: str) -> bool:
    return name in db().list_tables().tables


def ensure_table(name: str, schema: pa.Schema, recreate: bool = False):
    if recreate and has_table(name):
        db().drop_table(name)
    return db().open_table(name) if has_table(name) else db().create_table(name, schema=schema)


def upsert(name: str, rows: list[dict]) -> None:
    """Insère ou remplace par `id` : relancer une ingestion met à jour au lieu de dupliquer."""
    table = db().open_table(name)
    data = pa.Table.from_pylist(rows, schema=table.schema)
    table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)


def quote(value: str) -> str:
    """Littéral SQL pour les filtres `where` (les valeurs viennent du modèle : on échappe)."""
    return "'" + value.replace("'", "''") + "'"


def vector_field(dim: int) -> pa.Field:
    return pa.field("vector", pa.list_(pa.float32(), dim))


def search(name: str, vector: list[float], where: str | None = None, limit: int = 10) -> list[dict]:
    """Plus proches voisins (cosinus), filtre appliqué avant la recherche. Ajoute `score` = similarité."""
    q = db().open_table(name).search(vector).distance_type("cosine").limit(limit)
    if where:
        q = q.where(where, prefilter=True)
    rows = q.to_list()
    for r in rows:
        r["score"] = 1 - r.pop("_distance")
        r.pop("vector", None)
    return rows


def select(name: str, where: str | None = None, columns: list[str] | None = None, limit: int = 1000) -> list[dict]:
    """Lecture filtrée sans recherche vectorielle (fiche complète, voisins, agrégats)."""
    table = db().open_table(name)
    q = table.search().limit(limit)
    if where:
        q = q.where(where)
    q = q.select(columns or [f for f in table.schema.names if f != "vector"])
    return q.to_list()


def count(name: str) -> int:
    return db().open_table(name).count_rows() if has_table(name) else 0


def bounds(name: str, column: str) -> tuple | None:
    """(min, max) d'une colonne, en ne lisant que cette colonne. None si la table est absente ou vide."""
    if not has_table(name):
        return None
    table = db().open_table(name)
    n = table.count_rows()
    if n == 0:
        return None
    col = table.search().select([column]).limit(n).to_arrow().column(column)
    mm = pc.min_max(col).as_py()
    return mm["min"], mm["max"]
