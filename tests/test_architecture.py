"""Garde-fou de l'architecture hexagonale : le cœur ne dépend ni des adaptateurs ni des contextes."""

import ast
from pathlib import Path

SRC = Path(__file__).parents[1] / "src" / "agora"
STDLIB_OK = {"json", "re", "time", "datetime", "collections", "dataclasses", "typing", "abc", "enum"}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_le_coeur_n_importe_que_la_stdlib_et_lui_meme():
    for path in (SRC / "core").glob("*.py"):
        for name in imports(path):
            assert name.startswith("agora.core") or name.split(".")[0] in STDLIB_OK, f"{path.name} importe {name}"


def test_un_contexte_n_importe_pas_un_autre_contexte():
    contexts = [p.name for p in (SRC / "contexts").iterdir() if p.is_dir() and not p.name.startswith("_")]
    for ctx in contexts:
        for path in (SRC / "contexts" / ctx).glob("*.py"):
            for name in imports(path):
                others = [c for c in contexts if c != ctx]
                assert not any(name.startswith(f"agora.contexts.{o}") for o in others), f"{ctx}/{path.name} → {name}"
