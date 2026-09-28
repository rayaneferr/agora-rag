"""Export / import de l'index Qdrant sous forme de snapshots, pour ne pas refaire l'ingestion.

uv run agora-index export                 # Qdrant → data/snapshots/<collection>.snapshot
uv run agora-index publish                # data/snapshots/ → dataset Hugging Face
uv run agora-index import                 # data/snapshots/ (ou Hugging Face si absent) → Qdrant
uv run agora-index import --collection films
"""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx

from agora.adapters.outbound.vectorstore import DATA_DIR, EMBED_MODEL, QDRANT_URL, qdrant
from agora.contexts import CONTEXTS

SNAPSHOT_DIR = DATA_DIR / "snapshots"
COLLECTIONS = [c for spec in CONTEXTS.values() for c in spec.collections]
HF_REPO = os.getenv("AGORA_HF_REPO", "rferrat/agora-rag-index")
MANIFEST = "manifest.json"


def export(collections: list[str]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    client = qdrant()
    manifest_path = SNAPSHOT_DIR / MANIFEST
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"collections": {}}
    for name in collections:
        count = client.count(name, exact=True).count
        snap = client.create_snapshot(name, wait=True)
        target = SNAPSHOT_DIR / f"{name}.snapshot"
        with httpx.stream("GET", f"{QDRANT_URL}/collections/{name}/snapshots/{snap.name}", timeout=None) as r:
            r.raise_for_status()
            with target.open("wb") as f:
                for block in r.iter_bytes(1 << 20):
                    f.write(block)
        client.delete_snapshot(name, snap.name)  # la copie locale suffit, on libère le disque de Qdrant
        # L'index n'a de sens qu'avec le modèle qui l'a produit : on le trace avec le snapshot.
        manifest["collections"][name] = {
            "points": count,
            "embed_model": EMBED_MODEL,
            "qdrant_version": httpx.get(QDRANT_URL).json()["version"],
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "size_bytes": target.stat().st_size,
        }
        print(f"{name}: {count} points → {target} ({target.stat().st_size / 1e6:.0f} Mo)")
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def publish(collections: list[str]) -> None:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(HF_REPO, repo_type="dataset", exist_ok=True)
    files = [SNAPSHOT_DIR / f"{name}.snapshot" for name in collections] + [SNAPSHOT_DIR / MANIFEST]
    card = Path(__file__).parent / "dataset_card.md"
    for path in files:
        if not path.exists():
            raise SystemExit(f"{path} absent : lance d'abord `agora-index export`")
    for path in files:
        print(f"Upload {path.name} ({path.stat().st_size / 1e6:.0f} Mo)…")
        api.upload_file(path_or_fileobj=path, path_in_repo=path.name, repo_id=HF_REPO, repo_type="dataset")
    api.upload_file(path_or_fileobj=card, path_in_repo="README.md", repo_id=HF_REPO, repo_type="dataset")
    print(f"https://huggingface.co/datasets/{HF_REPO}")


def fetch(name: str) -> Path:
    """Snapshot local s'il existe, sinon téléchargé depuis Hugging Face (reprise + cache)."""
    local = SNAPSHOT_DIR / f"{name}.snapshot"
    if local.exists():
        return local
    from huggingface_hub import hf_hub_download

    print(f"{name}: téléchargement depuis huggingface.co/datasets/{HF_REPO}…")
    manifest = json.loads(Path(hf_hub_download(HF_REPO, MANIFEST, repo_type="dataset")).read_text())
    expected = manifest["collections"][name]["embed_model"]
    if expected != EMBED_MODEL:
        raise SystemExit(f"{name}: l'index a été construit avec {expected}, mais EMBED_MODEL={EMBED_MODEL}")
    return Path(hf_hub_download(HF_REPO, f"{name}.snapshot", repo_type="dataset"))


def restore(source: Path, collection: str) -> int:
    with source.open("rb") as f:
        r = httpx.post(
            f"{QDRANT_URL}/collections/{collection}/snapshots/upload",
            params={"priority": "snapshot", "wait": "true"},
            files={"snapshot": (source.name, f)},
            timeout=None,
        )
    r.raise_for_status()
    return qdrant().count(collection, exact=True).count


def import_(collections: list[str]) -> None:
    for name in collections:
        print(f"{name}: {restore(fetch(name), name)} points restaurés")


def ensure_index() -> None:
    """Restaure les collections absentes : appelé au démarrage de l'application."""
    client = qdrant()
    missing = [name for name in COLLECTIONS if not client.collection_exists(name)]
    if missing:
        import_(missing)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "publish", "import"])
    parser.add_argument("--collection", choices=COLLECTIONS, action="append", help="Par défaut : toutes")
    args = parser.parse_args()
    actions = {"export": export, "publish": publish, "import": import_}
    actions[args.action](args.collection or COLLECTIONS)


if __name__ == "__main__":
    main()
