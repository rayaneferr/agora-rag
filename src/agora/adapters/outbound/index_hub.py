"""Distribution de l'index LanceDB via Hugging Face, pour ne pas refaire l'ingestion (~2 h).

uv run agora-index export                 # compacte data/lancedb/ et écrit le manifeste
uv run agora-index publish                # data/lancedb/ → dataset Hugging Face
uv run agora-index import                 # dataset Hugging Face → data/lancedb/ (tables absentes)
uv run agora-index import --collection films

Une table LanceDB est un dossier de fichiers : l'import est un simple téléchargement, sans étape de restauration.
"""

import argparse
import json
import os
from datetime import UTC, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

from agora.adapters.outbound import vectorstore as vs
from agora.contexts import CONTEXTS

COLLECTIONS = [c for spec in CONTEXTS.values() for c in spec.collections]
HF_REPO = os.getenv("AGORA_HF_REPO", "rferrat/agora-rag-index")
MANIFEST = "manifest.json"
PREFIX = "lancedb"  # dossier de l'index dans le dataset


def _size(name: str) -> int:
    return sum(f.stat().st_size for f in (vs.DB_DIR / f"{name}.lance").rglob("*") if f.is_file())


def export(collections: list[str]) -> None:
    path = vs.DB_DIR / MANIFEST
    manifest = json.loads(path.read_text()) if path.exists() else {"collections": {}}
    for name in collections:
        table = vs.db().open_table(name)
        # Fusionne les fragments et supprime les anciennes versions : on publie l'état courant, rien d'autre.
        table.optimize(cleanup_older_than=timedelta(0))
        # L'index n'a de sens qu'avec le modèle qui l'a produit : on le trace avec les données.
        manifest["collections"][name] = {
            "rows": table.count_rows(),
            "embed_model": vs.EMBED_MODEL,
            "lancedb_version": version("lancedb"),
            "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "size_bytes": _size(name),
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
    print(f"https://huggingface.co/datasets/{HF_REPO}")


def import_(collections: list[str]) -> None:
    from huggingface_hub import hf_hub_download, snapshot_download

    manifest = json.loads(Path(hf_hub_download(HF_REPO, MANIFEST, repo_type="dataset")).read_text())
    for name in collections:
        expected = manifest["collections"][name]["embed_model"]
        if expected != vs.EMBED_MODEL:
            raise SystemExit(f"{name}: l'index a été construit avec {expected}, mais EMBED_MODEL={vs.EMBED_MODEL}")
        print(f"{name}: téléchargement depuis huggingface.co/datasets/{HF_REPO}…")
        snapshot_download(
            HF_REPO,
            repo_type="dataset",
            local_dir=vs.DB_DIR.parent,
            allow_patterns=f"{PREFIX}/{name}.lance/*",
        )
        print(f"{name}: {vs.count(name)} lignes")


def ensure_index() -> None:
    """Télécharge les tables absentes : appelé au démarrage de l'application."""
    missing = [name for name in COLLECTIONS if not vs.has_table(name)]
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
