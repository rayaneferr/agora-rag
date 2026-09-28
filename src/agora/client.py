"""Client conversationnel en ligne de commande : même boucle agent que l'interface web.

uv run agora-chat --model openai/gpt-5.4-mini
uv run agora-chat --model openai/gpt-5.4-mini --mcp-url cinema=http://localhost:8101/mcp
"""

import argparse
import asyncio
import getpass
import json
import os
import sys

import litellm
from mcp.client.session_group import ClientSessionGroup

from agora.agent import LLMError, Turn, connect_servers, run_turn


def resolve_api_key(model: str, cli_key: str | None) -> str | None:
    """Clé fournie en argument > variable d'env du provider (OPENAI_API_KEY…) > saisie interactive."""
    if cli_key or os.getenv("LLM_API_KEY"):
        return cli_key or os.getenv("LLM_API_KEY")
    missing = litellm.validate_environment(model).get("missing_keys", [])
    if not missing:
        return None  # LiteLLM trouvera la clé tout seul dans l'environnement
    return getpass.getpass(f"Clé API pour {model} ({', '.join(missing)}) : ").strip()


async def run(model: str, api_key: str | None, mcp_urls: dict[str, str]) -> None:
    async with ClientSessionGroup() as group:
        tool_servers = await connect_servers(group, mcp_urls)
        print(f"Modèle : {model} — outils MCP : {', '.join(tool_servers)}")
        print("Pose ta question (Ctrl-D pour quitter).\n")
        history: list[dict] = []
        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not question:
                continue
            turn = Turn(model=model, api_key=api_key, history=history, message=question)
            print()
            try:
                async for ev in run_turn(group, turn, tool_servers):
                    if ev["type"] == "token":
                        print(ev["text"], end="", flush=True)
                    elif ev["type"] == "tool_call":
                        print(f"  → {ev['name']}({json.dumps(ev['args'], ensure_ascii=False)})", file=sys.stderr)
                    elif ev["type"] == "done":
                        s = ev["stats"]
                        history += [
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": ev["content"]},
                        ]
                        tokens = s["prompt_tokens"] + s["completion_tokens"]
                        print(
                            f"\n\n[{s['total_ms'] / 1000:.1f}s · {tokens} tokens · "
                            f"${s['cost_usd']:.4f} · {s['tool_calls']} appels d'outils]\n",
                            file=sys.stderr,
                        )
                    elif ev["type"] == "error":
                        print(f"\n[{ev['message']}]\n", file=sys.stderr)
            except LLMError as exc:
                print(f"\n[{exc}]\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL"), help="Modèle au format LiteLLM (provider/modele)")
    parser.add_argument("--api-key", help="Clé API (sinon variable d'env ou saisie)")
    parser.add_argument(
        "--mcp-url",
        action="append",
        default=[],
        metavar="SERVEUR=URL",
        help="Serveur MCP HTTP déjà lancé, ex. cinema=http://localhost:8101/mcp (sinon lancement stdio local)",
    )
    args = parser.parse_args()
    if not args.model:
        parser.error("précise --model (ou LLM_MODEL dans .env)")
    urls = dict(u.split("=", 1) for u in args.mcp_url)
    litellm.suppress_debug_info = True
    asyncio.run(run(args.model, resolve_api_key(args.model, args.api_key), urls))


if __name__ == "__main__":
    main()
