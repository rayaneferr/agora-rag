"""Vérifie un déploiement des serveurs MCP publics, à travers le vrai protocole (Streamable HTTP).

uv run python scripts/smoke_test.py                                   # http://127.0.0.1:8100
uv run python scripts/smoke_test.py https://rferrat-agora-mcp.hf.space

Pour chaque contexte : /health, liste des outils, une vraie recherche, un prompt et la resource d'archives.
Code de sortie non nul au premier échec.
"""

import asyncio
import json
import sys
import time

import httpx
from mcp import Client

# Une recherche par contexte, dont on sait qu'elle doit trouver quelque chose dans l'index publié.
CHECKS = {
    "cinema": ("search_films", {"query": "a man relives the same day over and over", "limit": 3}),
    "assemblee": ("search_debats", {"query": "dette publique", "limit": 3}),
}
PROMPTS = {
    "cinema": ("trouver-un-film", {"souvenir": "un voleur dans les rêves"}),
    "assemblee": ("debat-sur-un-sujet", {"sujet": "la dette publique"}),
}


def step(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'✓' if ok else '✗'} {label}{f' — {detail}' if detail else ''}")
    if not ok:
        raise SystemExit(1)


async def check_context(base: str, cid: str) -> None:
    tool, args = CHECKS[cid]
    async with Client(f"{base}/{cid}/mcp") as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        step(f"{cid} : outils", tool in tools, ", ".join(sorted(tools)))

        start = time.perf_counter()
        result = await client.call_tool(tool, args)
        elapsed = time.perf_counter() - start
        hits = (result.structured_content or {}).get("result") or []
        first = hits[0].get("title") or hits[0].get("orateur") if hits else None
        step(
            f"{cid} : {tool}",
            not result.is_error and bool(hits),
            f"{len(hits)} résultats, 1er : {first}, {elapsed:.2f} s",
        )

        name, prompt_args = PROMPTS[cid]
        prompt = await client.get_prompt(name, prompt_args)
        step(f"{cid} : prompt {name}", "Règles :" in prompt.messages[0].content.text)

        archives = json.loads((await client.read_resource(f"{cid}://archives")).contents[0].text)
        step(f"{cid} : {cid}://archives", archives["extraits_indexes"] > 0, archives["etendue"] or "")


async def main(base: str) -> None:
    base = base.rstrip("/")
    # Au démarrage, /health répond 503 « starting » le temps de charger bge-m3 : on attend, 3 min au plus.
    for _ in range(36):
        health = httpx.get(f"{base}/health", timeout=30)
        body = health.json()
        if body["status"] != "starting":
            break
        print("… bge-m3 en cours de chargement")
        await asyncio.sleep(5)
    step("/health", health.status_code == 200 and body["status"] == "ok", body["status"])
    for cid in body["contexts"]:
        await check_context(base, cid)
    print("Déploiement opérationnel.")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"))
