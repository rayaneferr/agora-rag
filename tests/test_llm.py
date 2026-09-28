"""Normalisation des sorties de modèles locaux."""

import json

from agora.adapters.outbound.llm import recover_tool_calls

TOOLS = [{"type": "function", "function": {"name": "search_debats", "parameters": {}}}]


def test_appel_ecrit_en_texte_devient_un_appel_d_outil():
    msg = {"role": "assistant", "content": '🏛 {"name": "search_debats", "arguments": {"query": "IA"}} </tool_call>'}
    out = recover_tool_calls(msg, TOOLS)
    assert out["content"] == ""
    [call] = out["tool_calls"]
    assert call["function"]["name"] == "search_debats"
    assert json.loads(call["function"]["arguments"]) == {"query": "IA"}


def test_texte_ordinaire_inchange():
    for content in ['Le champ "name" est vide.', '{"name": "outil_inconnu", "arguments": {}}', "Réponse normale."]:
        msg = {"role": "assistant", "content": content}
        assert recover_tool_calls(msg, TOOLS) is msg


def test_appel_deja_structure_inchange():
    msg = {"role": "assistant", "content": "", "tool_calls": [{"id": "x"}]}
    assert recover_tool_calls(msg, TOOLS) is msg
