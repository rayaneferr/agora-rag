"""Export / import de l'index Qdrant sous forme de snapshots, pour ne pas refaire l'ingestion.

uv run agora-index export                 # → data/snapshots/<collection>.snapshot
uv run agora-index import                 # data/snapshots/*.snapshot → Qdrant
uv run agora-index import --collection films
"""

import argparse

import httpx

from agora.common import COLLECTION_DEBATS, COLLECTION_FILMS, DATA_DIR, QDRANT_URL, qdrant

SNAPSHOT_DIR = DATA_DIR / "snapshots"
COLLECTIONS = [COLLECTION_FILMS, COLLECTION_DEBATS]


def export(collections: list[str]) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    client = qdrant()
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
        print(f"{name}: {count} points → {target} ({target.stat().st_size / 1e6:.0f} Mo)")


def import_(collections: list[str]) -> None:
    for name in collections:
        source = SNAPSHOT_DIR / f"{name}.snapshot"
        if not source.exists():
            print(f"{name}: {source} absent, ignoré")
            continue
        with source.open("rb") as f:
            r = httpx.post(
                f"{QDRANT_URL}/collections/{name}/snapshots/upload",
                params={"priority": "snapshot", "wait": "true"},
                files={"snapshot": (source.name, f)},
                timeout=None,
            )
        r.raise_for_status()
        print(f"{name}: {qdrant().count(name, exact=True).count} points restaurés")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("--collection", choices=COLLECTIONS, action="append", help="Par défaut : toutes")
    args = parser.parse_args()
    (export if args.action == "export" else import_)(args.collection or COLLECTIONS)


if __name__ == "__main__":
    main()
