"""Intégrité de l'index distribué : chaque fichier est comparé aux empreintes de la révision épinglée."""

import hashlib

import pytest

from agora.adapters.outbound import index_hub as hub
from agora.adapters.outbound.mcp_serve import is_loopback


def _remote(path: str, data: bytes, lfs: bool) -> hub.RemoteFile:
    sha256 = hashlib.sha256(data).hexdigest() if lfs else None
    blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
    return hub.RemoteFile(path, len(data), sha256, blob)


def test_verify_accepte_des_fichiers_conformes(tmp_path):
    big, small = b"x" * 5000, b'{"v": 1}'
    (tmp_path / "t.lance").mkdir()
    (tmp_path / "t.lance" / "data.lance").write_bytes(big)
    (tmp_path / "t.lance" / "hint.json").write_bytes(small)
    hub.verify(tmp_path, [_remote("t.lance/data.lance", big, True), _remote("t.lance/hint.json", small, False)])


def test_verify_refuse_fichier_modifie_tronque_ou_absent(tmp_path):
    data = b"y" * 3000
    files = [_remote("a.lance", data, True), _remote("b.json", b"{}", False), _remote("c.json", b"{}", False)]
    (tmp_path / "a.lance").write_bytes(b"z" * 3000)  # même taille, contenu différent
    (tmp_path / "b.json").write_bytes(b"{")  # tronqué
    with pytest.raises(hub.IntegrityError) as exc:
        hub.verify(tmp_path, files)
    message = str(exc.value)
    assert "a.lance: empreinte différente" in message
    assert "b.json: 1 octets au lieu de 2" in message
    assert "c.json: absent" in message


def test_revision_epinglee_est_un_commit():
    assert len(hub.INDEX_REVISION) == 40 and int(hub.INDEX_REVISION, 16)


def test_serveur_mcp_http_distingue_la_boucle_locale():
    assert is_loopback("127.0.0.1") and is_loopback("localhost") and is_loopback("::1")
    assert not is_loopback("0.0.0.0") and not is_loopback("192.168.1.10") and not is_loopback("monpc")
