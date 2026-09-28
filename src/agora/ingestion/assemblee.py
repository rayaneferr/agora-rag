"""Ingestion des comptes rendus de séance de l'Assemblée nationale (17e législature)
dans la collection Qdrant `debats`. Unité = une intervention (paragraphes consécutifs
d'un même orateur sous un même point de l'ordre du jour).

uv run python -m agora.ingestion.assemblee [--limit-seances 10]
"""

import argparse
import re
import urllib.request
import uuid
import zipfile
from collections.abc import Iterator
from datetime import date

from lxml import etree
from qdrant_client import models

from agora.common import COLLECTION_DEBATS, DATA_DIR, chunk_text, embed, embedding_dim, qdrant

ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/vp/syceronbrut/syseron.xml.zip"
ZIP_PATH = DATA_DIR / "an17_syceron.xml.zip"
NS = {"an": "http://schemas.assemblee-nationale.fr/referentiel"}
MIN_CHARS = 120  # sous ce seuil : « La parole est à… », « Très bien ! », etc.
BATCH = 128


def text_of(el) -> str:
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip() if el is not None else ""


def parse_seance(xml_bytes: bytes) -> Iterator[dict]:
    root = etree.fromstring(xml_bytes)
    uid = root.findtext("an:uid", namespaces=NS)
    raw_date = root.findtext("an:metadonnees/an:dateSeance", namespaces=NS)  # 20241106140000000
    d = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))

    section, sujet = "", ""
    current: dict | None = None

    def flush():
        if current and len(current["text"]) >= MIN_CHARS:
            yield current

    for el in root.iter("{*}point", "{*}paragraphe"):
        if el.tag.endswith("point"):
            yield from flush()
            current = None
            title = text_of(el.find("an:texte", NS))
            if el.get("nivpoint") == "1":
                section, sujet = title, title
            else:
                sujet = title
            continue

        acteur = el.get("id_acteur")
        texte = text_of(el.find("an:texte", NS))
        if not acteur or not texte:
            continue  # didascalies : (Applaudissements…), (La séance est suspendue.)
        if el.get("roledebat") == "president":
            continue  # police de séance, pas de fond
        if current and current["id_acteur"] == acteur:
            current["text"] += "\n" + texte
            continue
        if current and len(texte) < MIN_CHARS:
            continue  # interjection d'un autre orateur (« Très bien ! ») : ne coupe pas l'intervention
        yield from flush()
        orateur = el.find("an:orateurs/an:orateur", NS)
        current = {
            "seance_uid": uid,
            "date": d.isoformat(),
            "date_int": int(d.strftime("%Y%m%d")),
            "section": section,
            "sujet": sujet,
            "ordre": int(el.get("ordre_absolu_seance", 0)),
            "id_acteur": acteur,
            "orateur": text_of(orateur.find("an:nom", NS)) if orateur is not None else "",
            "qualite": text_of(orateur.find("an:qualite", NS)) if orateur is not None else "",
            "role": el.get("roledebat") or "",
            "text": texte,
            "url": f"https://www.assemblee-nationale.fr/dyn/17/comptes-rendus/seance/{uid}",
        }
    yield from flush()


def iter_interventions(limit_seances: int | None) -> Iterator[dict]:
    if not ZIP_PATH.exists():
        DATA_DIR.mkdir(exist_ok=True)
        print(f"Téléchargement {ZIP_URL}")
        urllib.request.urlretrieve(ZIP_URL, ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = sorted(n for n in zf.namelist() if n.endswith(".xml"))
        for name in names[:limit_seances] if limit_seances else names:
            yield from parse_seance(zf.read(name))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-seances", type=int, help="Nombre de séances (pour tester vite)")
    parser.add_argument("--recreate", action="store_true", help="Supprime la collection avant")
    args = parser.parse_args()

    client = qdrant()
    if args.recreate and client.collection_exists(COLLECTION_DEBATS):
        client.delete_collection(COLLECTION_DEBATS)
    if not client.collection_exists(COLLECTION_DEBATS):
        client.create_collection(
            COLLECTION_DEBATS,
            vectors_config=models.VectorParams(size=embedding_dim(), distance=models.Distance.COSINE),
        )
        for field in ("orateur", "id_acteur", "seance_uid"):
            client.create_payload_index(COLLECTION_DEBATS, field, models.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION_DEBATS, "date_int", models.PayloadSchemaType.INTEGER)
        client.create_payload_index(COLLECTION_DEBATS, "ordre", models.PayloadSchemaType.INTEGER)
        client.create_payload_index(COLLECTION_DEBATS, "sujet", models.PayloadSchemaType.TEXT)

    batch: list[tuple[str, dict]] = []
    total = 0

    def push():
        nonlocal total
        vectors = embed([t for t, _ in batch])
        client.upsert(
            COLLECTION_DEBATS,
            points=[
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{p['seance_uid']}/{p['ordre']}/{p['chunk_index']}")),
                    vector=v,
                    payload=p,
                )
                for v, (_, p) in zip(vectors, batch)
            ],
        )
        total += len(batch)
        print(f"  {total} chunks indexés")
        batch.clear()

    for inter in iter_interventions(args.limit_seances):
        for i, chunk in enumerate(chunk_text(inter["text"])):
            # Contexte en tête de chunk : qui parle, de quoi — sinon « je suis contre » ne veut rien dire.
            header = f"{inter['orateur']} ({inter['date']}) — {inter['sujet']}"
            batch.append((f"{header}\n{chunk}", {**inter, "chunk_index": i, "text": chunk}))
        if len(batch) >= BATCH:
            push()
    if batch:
        push()


if __name__ == "__main__":
    main()
