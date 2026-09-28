"""Adaptateur entrant CLI : même agent que l'interface web, dans le terminal.

uv run agora-chat cinema
uv run agora-chat assemblee --model qwen2.5:7b
uv run agora-chat cinema --mcp-url http://localhost:8101/mcp
"""

import argparse
import asyncio
import json
import sys

import litellm

from agora.adapters.outbound import llm
from agora.adapters.outbound.mcp import McpGateway
from agora.contexts import CONTEXTS
from agora.core.agent import LLMError, Turn, run_turn


async def run(context: str, model: str, mcp_url: str | None) -> None:
    spec = CONTEXTS[context]
    async with McpGateway(spec, url=mcp_url) as gateway:
        print(
            f"{spec.identity.place} — {spec.identity.agent} · modèle {model} · outils {', '.join(gateway.tool_names)}"
        )
        print("Pose ta question (Ctrl-D pour quitter).\n")
        history: list[dict] = []
        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not question:
                continue
            print()
            try:
                async for ev in run_turn(spec, llm.make_llm("ollama", model), gateway, Turn(question, history)):
                    if ev["type"] == "token":
                        print(ev["text"], end="", flush=True)
                    elif ev["type"] == "tool_call":
                        print(f"  → {ev['name']}({json.dumps(ev['args'], ensure_ascii=False)})", file=sys.stderr)
                    elif ev["type"] == "done":
                        history += [
                            {"role": "user", "content": question},
                            {"role": "assistant", "content": ev["content"]},
                        ]
                        s = ev["stats"]
                        tokens = s["prompt_tokens"] + s["completion_tokens"]
                        print(
                            f"\n\n[{s['total_ms'] / 1000:.1f}s · {tokens} tokens · {s['tool_calls']} outils]\n",
                            file=sys.stderr,
                        )
                    elif ev["type"] == "error":
                        print(f"\n[{ev['message']}]\n", file=sys.stderr)
            except LLMError as exc:
                print(f"\n[{exc}]\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("context", choices=list(CONTEXTS))
    parser.add_argument("--model", default=llm.PREFERRED[0], help="Modèle Ollama (défaut : %(default)s)")
    parser.add_argument("--mcp-url", help="Serveur MCP HTTP déjà lancé (sinon lancement stdio local)")
    args = parser.parse_args()
    litellm.suppress_debug_info = True
    asyncio.run(run(args.context, args.model, args.mcp_url))


if __name__ == "__main__":
    main()
