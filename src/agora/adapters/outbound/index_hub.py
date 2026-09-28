"""Distribution de l'index LanceDB via Hugging Face, pour ne pas refaire l'ingestion (~2 h).

uv run agora-index export                 # compacte data/lancedb/ et écrit le manifeste (avec empreintes)
uv run agora-index publish                # data/lancedb/ → dataset Hugging Face
uv run agora-index import                 # dataset Hugging Face → data/lancedb/ (tables absentes) + bge-m3
uv run agora-index import --collection films
uv run agora-index verify                 # compare data/lancedb/ à la révision épinglée

Une table LanceDB est un dossier de fichiers : l'import est un simple téléchargement, sans étape de restauration.

Intégrité : le code épingle une révision (commit) du dataset et du modèle d'embeddings. Chaque fichier
téléchargé est comparé à l'empreinte que Hugging Face publie pour cette révision (sha256 des fichiers LFS,
sha1 git des autres). Un fichier remplacé sur le Hub, ou tronqué en route, est refusé.
"""

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

from agora.adapters.outbound import vectorstore as vs
from agora.contexts import CONTEXTS

COLLECTIONS = [c for spec in CONTEXTS.values() for c in spec.collections]
HF_REPO = os.getenv("AGORA_HF_REPO", "rferrat/agora-rag-index")
# Commit du dataset que l'application accepte. À mettre à jour à chaque `agora-index publish`.
INDEX_REVISION = os.getenv("AGORA_INDEX_REVISION", "fc60445f270a8617ce109eaef423a4873ed0fb2a")
MANIFEST = "manifest.json"
PREFIX = "lancedb"  # dossier de l'index dans le dataset
# Le dépôt bge-m3 contient aussi un export ONNX (2,3 Go) et des images : inutiles ici.
EMBED_IGNORE = ["onnx/*", "imgs/*", "*.jpg", "*.webp", "*.pt", "*.DS_Store"]


class IntegrityError(RuntimeError):
    """Un fichier téléchargé ne correspond pas à la révision épinglée."""


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    sha256: str | None  # fichiers LFS
    blob_id: str  # sha1 git, pour les petits fichiers


def remote_files(repo: str, repo_type: str, revision: str, prefix: str = "") -> list[RemoteFile]:
    """Les fichiers d'une révision et leurs empreintes, telles que le Hub les publie."""
    from huggingface_hub import HfApi

    info = HfApi().repo_info(repo, repo_type=repo_type, revision=revision, files_metadata=True)
    files = []
    for s in info.siblings:
        if not s.rfilename.startswith(prefix):
            continue
        lfs = s.lfs
        sha = (lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)) if lfs else None
        files.append(RemoteFile(s.rfilename, s.size or 0, sha, s.blob_id or ""))
    return files


def _digest(path: Path, sha256: bool, size: int) -> str:
    h = hashlib.sha256() if sha256 else hashlib.sha1(f"blob {size}\0".encode())
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify(local_dir: Path, files: list[RemoteFile]) -> None:
    """Chaque fichier local doit exister, faire la bonne taille et porter la bonne empreinte."""
    problems = []
    for f in files:
        path = local_dir / f.path
        if not path.is_file():
            problems.append(f"{f.path}: absent")
        elif path.stat().st_size != f.size:
            problems.append(f"{f.path}: {path.stat().st_size} octets au lieu de {f.size}")
        elif _digest(path, bool(f.sha256), f.size) != (f.sha256 or f.blob_id):
            problems.append(f"{f.path}: empreinte différente de la révision {INDEX_REVISION[:10]}")
    if problems:
        raise IntegrityError("Index refusé :\n  " + "\n  ".join(problems))


def download_progress(local_dir: Path, files: list[RemoteFile]) -> tuple[int, int]:
    """(octets présents, octets attendus) : les fichiers finis plus les téléchargements en cours."""
    total = sum(f.size for f in files)
    done = sum(min((local_dir / f.path).stat().st_size, f.size) for f in files if (local_dir / f.path).is_file())
    partial = local_dir / ".cache" / "huggingface" / "download"
    if partial.is_dir():
        done += sum(p.stat().st_size for p in partial.rglob("*.incomplete"))
    return min(done, total), total


def _size(name: str) -> int:
    return sum(f.stat().st_size for f in (vs.DB_DIR / f"{name}.lance").rglob("*") if f.is_file())


def export(collections: list[str]) -> None:
    path = vs.DB_DIR / MANIFEST
    manifest = json.loads(path.read_text()) if path.exists() else {"collections": {}}
    for name in collections:
        table = vs.db().open_table(name)
        # Fusionne les fragments et supprime les anciennes versions : on publie l'état courant, rien d'autre.
        table.optimize(cleanup_older_than=timedelta(0))
        folder = vs.DB_DIR / f"{name}.lance"
        # L'index n'a de sens qu'avec le modèle qui l'a produit : on le trace avec les données.
        manifest["collections"][name] = {
            "rows": table.count_rows(),
            "embed_model": vs.EMBED_MODEL,
            "embed_revision": vs.EMBED_REVISION,
            "lancedb_version": version("lancedb"),
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "size_bytes": _size(name),
            "files": {
                str(f.relative_to(folder)): _digest(f, True, f.stat().st_size)
                for f in sorted(folder.rglob("*"))
                if f.is_file()
            },
        }
        print(f"{name}: {table.count_rows()} lignes ({_size(name) / 1e6:.0f} Mo)")
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def publish(collections: list[str]) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(HF_REPO, repo_type="dataset", exist_ok=True)
    if not (vs.DB_DIR / MANIFEST).exists():
        raise SystemExit("manifeste absent : lance d'abord `agora-index export`")
    for name in collections:
        print(f"Upload {name} ({_size(name) / 1e6:.0f} Mo)…")
        api.upload_folder(
            folder_path=vs.DB_DIR / f"{name}.lance",
            path_in_repo=f"{PREFIX}/{name}.lance",
            repo_id=HF_REPO,
            repo_type="dataset",
            delete_patterns="*",  # remplace la version précédente au lieu d'y ajouter des fichiers
        )
    api.upload_file(path_or_fileobj=vs.DB_DIR / MANIFEST, path_in_repo=MANIFEST, repo_id=HF_REPO, repo_type="dataset")
    card = vs.ROOT / "src/agora/adapters/outbound/dataset_card.md"
    api.upload_file(path_or_fileobj=card, path_in_repo="README.md", repo_id=HF_REPO, repo_type="dataset")
    sha = api.dataset_info(HF_REPO).sha
    print(f"https://huggingface.co/datasets/{HF_REPO}/tree/{sha}")
    print(f"Nouvelle révision : {sha}\nÀ reporter dans INDEX_REVISION (index_hub.py) pour que l'application l'accepte.")


def index_files(name: str) -> list[RemoteFile]:
    return remote_files(HF_REPO, "dataset", INDEX_REVISION, prefix=f"{PREFIX}/{name}.lance/")


def read_manifest() -> dict:
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(HF_REPO, MANIFEST, repo_type="dataset", revision=INDEX_REVISION)
    return json.loads(Path(path).read_text())


def import_(collections: list[str], progress: dict | None = None) -> None:
    """Télécharge les tables demandées à la révision épinglée, puis vérifie chaque fichier.

    `progress` (optionnel) reçoit {"done", "total"} en octets, mis à jour par l'appelant via download_progress.
    """
    from huggingface_hub import snapshot_download

    manifest = read_manifest()
    for name in collections:
        expected = manifest["collections"][name]["embed_model"]
        if expected != vs.EMBED_MODEL:
            raise SystemExit(f"{name}: l'index a été construit avec {expected}, mais EMBED_MODEL={vs.EMBED_MODEL}")
        files = index_files(name)
        if progress is not None:
            progress.setdefault("files", []).extend(files)
        print(f"{name}: téléchargement depuis huggingface.co/datasets/{HF_REPO} @ {INDEX_REVISION[:10]}…")
        snapshot_download(
            HF_REPO,
            repo_type="dataset",
            revision=INDEX_REVISION,
            local_dir=vs.DB_DIR.parent,
            allow_patterns=f"{PREFIX}/{name}.lance/*",
        )
        verify(vs.DB_DIR.parent, files)
        print(f"{name}: {vs.count(name)} lignes, empreintes vérifiées")


def verify_local(collections: list[str]) -> None:
    for name in collections:
        verify(vs.DB_DIR.parent, index_files(name))
        print(f"{name}: conforme à la révision {INDEX_REVISION[:10]}")


def ensure_index(progress: dict | None = None) -> None:
    """Télécharge les tables absentes : appelé au démarrage de l'application."""
    missing = [name for name in COLLECTIONS if not vs.has_table(name)]
    if missing:
        import_(missing, progress)


# --- modèle d'embeddings -------------------------------------------------------------------------------------


def embedder_files() -> list[RemoteFile]:
    from huggingface_hub.utils import filter_repo_objects

    files = remote_files(vs.EMBED_MODEL, "model", vs.EMBED_REVISION)
    kept = set(filter_repo_objects([f.path for f in files], ignore_patterns=EMBED_IGNORE))
    return [f for f in files if f.path in kept]


def embedder_ready() -> bool:
    """Le modèle est-il complet dans le cache local ? (aucun accès réseau)"""
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        snapshot_download(
            vs.EMBED_MODEL, revision=vs.EMBED_REVISION, ignore_patterns=EMBED_IGNORE, local_files_only=True
        )
        return True
    except (LocalEntryNotFoundError, OSError, ValueError):
        return False


def embedder_progress(files: list[RemoteFile]) -> tuple[int, int]:
    """Octets du modèle déjà dans le cache Hugging Face (blobs finis et en cours)."""
    from huggingface_hub.constants import HF_HUB_CACHE

    blobs = Path(HF_HUB_CACHE) / f"models--{vs.EMBED_MODEL.replace('/', '--')}" / "blobs"
    total = sum(f.size for f in files)
    done = sum(p.stat().st_size for p in blobs.glob("*") if p.is_file()) if blobs.is_dir() else 0
    return min(done, total), total


def ensure_embedder() -> None:
    """Télécharge bge-m3 (~2,3 Go) une fois pour toutes, hors du sous-processus MCP : l'attente est visible."""
    from huggingface_hub import snapshot_download

    if embedder_ready():
        return
    print(f"{vs.EMBED_MODEL}: téléchargement du modèle d'embeddings @ {vs.EMBED_REVISION[:10]}…")
    snapshot_download(vs.EMBED_MODEL, revision=vs.EMBED_REVISION, ignore_patterns=EMBED_IGNORE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "publish", "import", "verify"])
    parser.add_argument("--collection", choices=COLLECTIONS, action="append", help="Par défaut : toutes")
    args = parser.parse_args()
    collections = args.collection or COLLECTIONS
    if args.action == "export":
        export(collections)
    elif args.action == "publish":
        publish(collections)
    elif args.action == "verify":
        verify_local(collections)
    else:
        import_(collections)
        ensure_embedder()


if __name__ == "__main__":
    main()
