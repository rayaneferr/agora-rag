"""Client conversationnel : n'importe quel LLM (via LiteLLM, clé fournie par l'utilisateur)
branché sur les serveurs MCP « cinema » et « assemblee ».

uv run agora-chat --model anthropic/claude-sonnet-5
uv run agora-chat --model openai/gpt-5.4-mini
"""

import argparse
import asyncio
import getpass
import json
import os
import sys
import time

import litellm
from mcp.client.session_group import ClientSessionGroup
from mcp.client.stdio import StdioServerParameters

from agora.common import ROOT

SERVERS = ["agora.servers.cinema", "agora.servers.assemblee"]
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = """Tu es un assistant spécialisé en cinéma et en vie parlementaire française.
Tu disposes d'outils de recherche sur deux bases : des synopsis de films et les comptes rendus
de l'Assemblée nationale. Appuie-toi sur ces outils plutôt que sur ta mémoire, reformule ou relance
une recherche si les résultats sont mauvais, et cite tes sources (titre + année, ou orateur + date + URL).
Si les outils ne trouvent rien, dis-le au lieu d'inventer. Réponds en français."""


def resolve_api_key(model: str, cli_key: str | None) -> str | None:
    """Clé fournie en argument > variable d'env du provider (OPENAI_API_KEY…) > saisie interactive."""
    if cli_key or os.getenv("LLM_API_KEY"):
        return cli_key or os.getenv("LLM_API_KEY")
    missing = litellm.validate_environment(model).get("missing_keys", [])
    if not missing:
        return None  # LiteLLM trouvera la clé tout seul dans l'environnement
    return getpass.getpass(f"Clé API pour {model} ({', '.join(missing)}) : ").strip()


def to_openai_tools(group: ClientSessionGroup) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {"name": name, "description": tool.description or "", "parameters": tool.input_schema},
        }
        for name, tool in group.tools.items()
    ]


def result_to_text(result) -> str:
    if result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False)
    return "\n".join(getattr(c, "text", "") for c in result.content)


async def answer(group, tools, messages, model, api_key) -> dict:
    """Boucle agent : le LLM appelle des outils MCP jusqu'à pouvoir répondre."""
    stats = {"latency_s": 0.0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "tool_calls": 0}
    for _ in range(MAX_TOOL_ROUNDS):
        t0 = time.perf_counter()
        resp = await litellm.acompletion(model=model, messages=messages, tools=tools, api_key=api_key)
        stats["latency_s"] += time.perf_counter() - t0
        stats["prompt_tokens"] += resp.usage.prompt_tokens
        stats["completion_tokens"] += resp.usage.completion_tokens
        try:
            stats["cost_usd"] += litellm.completion_cost(resp)
        except Exception:
            pass  # modèle absent de la grille de prix LiteLLM

        msg = resp.choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            print(f"\n{msg.content}\n")
            return stats

        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            print(f"  → {call.function.name}({json.dumps(args, ensure_ascii=False)})", file=sys.stderr)
            t0 = time.perf_counter()
            result = await group.call_tool(call.function.name, args)
            stats["latency_s"] += time.perf_counter() - t0
            stats["tool_calls"] += 1
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result_to_text(result)})
    print("\n[Arrêt : trop d'appels d'outils sans réponse finale]\n")
    return stats


async def run(model: str, api_key: str | None) -> None:
    async with ClientSessionGroup() as group:
        for module in SERVERS:
            await group.connect_to_server(
                StdioServerParameters(command=sys.executable, args=["-m", module], cwd=str(ROOT))
            )
        tools = to_openai_tools(group)
        print(f"Modèle : {model} — outils MCP : {', '.join(group.tools)}")
        print("Pose ta question (Ctrl-D pour quitter).\n")

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        while True:
            try:
                question = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                return
            if not question:
                continue
            messages.append({"role": "user", "content": question})
            s = await answer(group, tools, messages, model, api_key)
            print(
                f"[{s['latency_s']:.1f}s · {s['prompt_tokens']}+{s['completion_tokens']} tokens · "
                f"${s['cost_usd']:.4f} · {s['tool_calls']} appels d'outils]\n",
                file=sys.stderr,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default=os.getenv("LLM_MODEL"), help="Modèle au format LiteLLM (provider/modele)")
    parser.add_argument("--api-key", help="Clé API (sinon variable d'env ou saisie)")
    args = parser.parse_args()
    if not args.model:
        parser.error("précise --model (ou LLM_MODEL dans .env)")
    litellm.suppress_debug_info = True
    asyncio.run(run(args.model, resolve_api_key(args.model, args.api_key)))


if __name__ == "__main__":
    main()
