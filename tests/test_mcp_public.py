"""App MCP publique : montage des contextes, protocole en HTTP, et garde-fous de l'exposition."""

import pytest
from starlette.testclient import TestClient

from agora.adapters.inbound import mcp_public

pytestmark = pytest.mark.usefixtures("index")

HOST = "agora.example"
HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json", "host": HOST}


@pytest.fixture
def make_client():
    def make(**kwargs):
        kwargs.setdefault("allowed_hosts", [HOST])
        app = mcp_public.create_app(warm_up=lambda: None, **kwargs)  # pas de bge-m3 pendant les tests
        return TestClient(app, base_url=f"http://{HOST}")

    return make


def rpc(client, path: str, method: str, params: dict | None = None, headers: dict | None = None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post(path, json=body, headers={**HEADERS, **(headers or {})})


def test_health_decrit_chaque_contexte(make_client):
    with make_client() as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["contexts"]["cinema"]["endpoint"] == "/cinema/mcp"
    assert body["contexts"]["assemblee"]["etendue"] == "séances du 6 novembre 2024 au 6 novembre 2024"


def test_chaque_contexte_a_ses_outils(make_client):
    with make_client() as client:
        cinema = rpc(client, "/cinema/mcp", "tools/list").json()["result"]["tools"]
        assemblee = rpc(client, "/assemblee/mcp", "tools/list").json()["result"]["tools"]
    assert {t["name"] for t in cinema} == {"search_films", "get_film"}
    assert {t["name"] for t in assemblee} == {"find_orateurs", "search_debats", "get_contexte"}


def test_appel_d_outil_en_http(make_client):
    params = {"name": "search_films", "arguments": {"query": "weatherman living the same day again"}}
    with make_client() as client:
        result = rpc(client, "/cinema/mcp", "tools/call", params).json()["result"]
    assert result["structuredContent"]["result"][0]["title"] == "Groundhog Day"


def test_host_inconnu_refuse(make_client):
    with make_client() as client:
        assert rpc(client, "/cinema/mcp", "tools/list", headers={"host": "evil.example"}).status_code == 421
        # La boucle locale reste acceptée, pour tester le conteneur depuis la machine.
        assert rpc(client, "/cinema/mcp", "tools/list", headers={"host": "127.0.0.1:8100"}).status_code == 200


def test_origine_inconnue_refusee(make_client):
    with make_client() as client:
        refused = rpc(client, "/cinema/mcp", "tools/list", headers={"origin": "https://evil.example"})
        accepted = rpc(client, "/cinema/mcp", "tools/list", headers={"origin": f"https://{HOST}"})
    assert refused.status_code == 403
    assert accepted.status_code == 200


def test_corps_trop_gros_refuse(make_client):
    params = {"name": "search_films", "arguments": {"query": "x" * (mcp_public.MAX_BODY_BYTES + 1)}}
    with make_client() as client:
        assert rpc(client, "/cinema/mcp", "tools/call", params).status_code == 413


def test_limite_de_debit_par_ip(make_client):
    with make_client(rate_limit=3) as client:
        codes = [rpc(client, "/cinema/mcp", "tools/list").status_code for _ in range(4)]
        limited = rpc(client, "/assemblee/mcp", "tools/list")
        health = client.get("/health")  # la sonde d'état n'est pas limitée
    assert codes == [200, 200, 200, 429]
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    assert health.status_code == 200


def test_ip_derriere_un_proxy():
    scope = {"client": ("10.0.0.1", 1234), "headers": [(b"x-forwarded-for", b"6.6.6.6, 1.2.3.4")]}
    assert mcp_public.client_ip(scope, 0) == "10.0.0.1"  # sans proxy de confiance, l'en-tête est ignoré
    assert mcp_public.client_ip(scope, 1) == "1.2.3.4"  # l'entrée ajoutée par le proxy, pas celle du client
    assert mcp_public.client_ip(scope, 3) == "10.0.0.1"  # chaîne plus courte qu'attendu : on ne la croit pas
