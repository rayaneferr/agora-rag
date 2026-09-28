"""Adaptateur HTTP : points d'entrée, cadrage SSE et garde-fous, avec le modèle de démo."""

import json

import pytest
from conftest import SERVERS, InMemoryGateway
from fastapi.testclient import TestClient

from agora.adapters.inbound import api
from agora.adapters.outbound import vectorstore as vs

pytestmark = pytest.mark.usefixtures("index")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGORA_DEMO", "1")
    monkeypatch.setattr(api, "_prepare", lambda: None)  # pas de téléchargement pendant les tests
    # Serveurs MCP en mémoire, sur la base temporaire : ni sous-processus, ni index réel, ni bge-m3.
    monkeypatch.setattr(api, "McpGateway", lambda spec: InMemoryGateway(SERVERS[spec.id]))
    api.state.index.status = "ready"
    api.state.coverage.clear()
    with TestClient(api.app, base_url="http://127.0.0.1") as c:
        yield c


def _events(response) -> list[dict]:
    frames = [f for f in response.text.split("\n\n") if f.strip()]
    assert all(f.startswith("data: ") for f in frames)
    return [json.loads(f[len("data: ") :]) for f in frames]


def test_host_inconnu_refuse(client):
    assert client.get("/api/health", headers={"host": "evil.example"}).status_code == 400
    assert client.get("/api/health", headers={"host": "localhost:8765"}).status_code == 200


def test_health_expose_l_etat_du_premier_lancement(client):
    body = client.get("/api/health").json()
    assert body["index"]["status"] == "ready"
    assert set(body["embedder"]) == {"status", "error", "done_bytes", "total_bytes"}


def test_contexts_avec_etendue_des_archives(client):
    contexts = {c["id"]: c for c in client.get("/api/contexts").json()}
    assert contexts["assemblee"]["coverage"] == "séances du 6 novembre 2024 au 6 novembre 2024"
    assert contexts["cinema"]["coverage"] == "films sortis de 1979 à 2010"
    assert contexts["cinema"]["points"] == vs.count("films")
    assert {t["name"] for t in contexts["cinema"]["tools"]} == {"search_films", "get_film"}


def test_chat_contexte_inconnu(client):
    body = {"context": "sport", "provider": "demo", "model": "demo", "message": "?"}
    assert client.post("/api/chat", json=body).status_code == 404


def test_chat_fournisseur_inconnu(client):
    body = {"context": "cinema", "provider": "openai", "model": "gpt", "message": "?"}
    assert client.post("/api/chat", json=body).status_code == 400


def test_chat_refuse_tant_que_les_archives_ne_sont_pas_la(client):
    api.state.index.status = "downloading"
    body = {"context": "cinema", "provider": "demo", "model": "demo", "message": "?"}
    assert client.post("/api/chat", json=body).status_code == 503


def test_chat_historique_role_invalide(client):
    body = {
        "context": "cinema",
        "provider": "demo",
        "model": "demo",
        "message": "?",
        "history": [{"role": "system", "content": "x"}],
    }
    assert client.post("/api/chat", json=body).status_code == 422


def test_chat_flux_sse_complet(client):
    body = {"context": "cinema", "provider": "demo", "model": "demo", "message": "weatherman same day"}
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    types = [e["type"] for e in events]
    assert types[0] == "thinking" and types[-1] == "done"
    assert "tool_call" in types and "tool_result" in types and "token" in types
    assert "Groundhog Day" in events[-1]["content"]
    assert "cost_usd" not in events[-1]["stats"]
