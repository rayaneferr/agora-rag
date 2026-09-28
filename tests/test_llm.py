"""Normalisation des sorties de modèles locaux et conversion vers l'API native d'Ollama."""

import json

from agora.adapters.outbound.llm import from_ollama_tool_calls, recover_tool_calls, to_ollama_messages

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


def test_messages_vers_ollama_arguments_en_objet():
    messages = [
        {"role": "system", "content": "s"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": '{"q": "x"}'}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "[]"},
    ]
    out = to_ollama_messages(messages)
    assert out[1] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": "f", "arguments": {"q": "x"}}}],
    }
    assert out[2] == {"role": "tool", "content": "[]"}


def test_arguments_illisibles_deviennent_un_objet_vide():
    msg = {"role": "assistant", "tool_calls": [{"function": {"name": "f", "arguments": "{pas du json"}}]}
    assert to_ollama_messages([msg])[0]["tool_calls"][0]["function"]["arguments"] == {}


def test_appels_ollama_recoivent_un_id_et_des_arguments_texte():
    [call] = from_ollama_tool_calls([{"function": {"name": "search_debats", "arguments": {"query": "IA"}}}])
    assert call["id"].startswith("call_") and call["type"] == "function"
    assert json.loads(call["function"]["arguments"]) == {"query": "IA"}
    [call] = from_ollama_tool_calls([{"id": "abc", "function": {"name": "f", "arguments": None}}])
    assert call["id"] == "abc" and call["function"]["arguments"] == "{}"
