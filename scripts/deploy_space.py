"""Déploie les serveurs MCP publics sur le Space Hugging Face (construit à partir du Dockerfile).

uv run python scripts/deploy_space.py              # crée le Space s'il n'existe pas, puis pousse le code
uv run python scripts/deploy_space.py --dry-run    # liste ce qui serait envoyé

Le Space ne reçoit que ce dont l'image a besoin (Dockerfile, dépendances verrouillées, src/), plus sa carte
(deploy/space/README.md). Un seul commit par déploiement ; les fichiers disparus du dépôt sont retirés du Space.
Authentification : le token de `hf auth login` (droit d'écriture sur l'espace du Space).
"""

import argparse
import subprocess
from pathlib import Path

from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi

ROOT = Path(__file__).resolve().parents[1]
SPACE = "rferrat/agora-mcp"
FILES = ["Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock", ".python-version"]
CARD = ROOT / "deploy" / "space" / "README.md"


def payload() -> dict[str, Path]:
    """Chemin dans le Space → fichier local. Seuls les fichiers suivis par git partent : rien de local ne fuit."""
    tracked = subprocess.run(["git", "ls-files", "src"], cwd=ROOT, capture_output=True, text=True, check=True)
    files = {name: ROOT / name for name in FILES}
    files |= {name: ROOT / name for name in tracked.stdout.split()}
    files["README.md"] = CARD
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--space", default=SPACE)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = payload()
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    watched = ["src", "deploy", *FILES]
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *watched], cwd=ROOT, capture_output=True, text=True)
    if dirty.stdout.strip() and not args.dry_run:
        raise SystemExit("Modifications non commitées : le Space doit correspondre à un commit du dépôt.")
    if args.dry_run:
        print("\n".join(sorted(files)))
        return

    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)
    remote = set(api.list_repo_files(args.space, repo_type="space"))
    stale = sorted(remote - set(files) - {".gitattributes"})
    operations = [CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(path)) for name, path in files.items()]
    operations += [CommitOperationDelete(path_in_repo=name) for name in stale]
    info = api.create_commit(
        args.space,
        repo_type="space",
        operations=operations,
        commit_message=f"Déploiement de rayaneferr/agora-rag@{commit.stdout.strip()}",
    )
    print(f"Poussé : {info.commit_url}")
    print(f"Construction : https://huggingface.co/spaces/{args.space}?logs=build")


if __name__ == "__main__":
    main()
