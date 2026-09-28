"""Ingestion des comptes rendus de séance de l'Assemblée nationale (17e législature)
dans la collection Qdrant `debats`. Unité = une intervention (paragraphes consécutifs
d'un même orateur sous un même point de l'ordre du jour).

uv run python -m agora.contexts.assemblee.ingestion [--limit-seances 10]
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

from agora.adapters.outbound.vectorstore import DATA_DIR, embed, embedding_dim, qdrant
from agora.contexts.assemblee import COLLECTION
from agora.core.text import chunk_text

ZIP_URL = "https://data.assemblee-nationale.fr/static/openData/repository/17/vp/syceronbrut/syseron.xml.zip"
ZIP_PATH = DATA_DIR / "an17_syceron.xml.zip"
NS = {"an": "http://schemas.assemblee-nationale.fr/referentiel"}
MIN_CHARS = 120  # sous ce seuil : « La parole est à… », « Très bien ! », etc.
BATCH = 128


# Titres de points qui ne disent rien du sujet. Les débats qui suivent une suspension sont rangés
# *dans* le point « Suspension et reprise de la séance » : on garde donc le titre précédent.
TITRES_IGNORES = re.compile(
    r"^(Suspension et reprise de la séance|Suite de la discussion d.*|Discussion des articles( \(suite\))?)$"
)


def text_of(el) -> str:
    return re.sub(r"\s+", " ", " ".join(el.itertext())).strip() if el is not None else ""


def split_orateur(raw: str) -> tuple[str, str | None, str | None]:
    """« M. Éric Coquerel (LFI-NFP) » → (« Éric Coquerel », « M. », « LFI-NFP »).

    Les comptes rendus écrivent le même orateur avec ou sans civilité, avec ou sans groupe :
    on normalise pour que filtres et agrégations portent sur une seule forme.
    """
    groupe = None
    if m := re.match(r"^(.*?)\s*\(([^()]+)\)$", raw):
        raw, groupe = m.group(1), m.group(2)
    civilite = None
    if m := re.match(r"^(M\.|Mme|Mlle)\s+(.*)$", raw):
        civilite, raw = m.group(1), m.group(2)
    return raw.strip(), civilite, groupe


def parse_seance(xml_bytes: bytes) -> Iterator[dict]:
    root = etree.fromstring(xml_bytes)
    uid = root.findtext("an:uid", namespaces=NS)
    raw_date = root.findtext("an:metadonnees/an:dateSeance", namespaces=NS)  # 20241106140000000
    d = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))

    # Passe 1 : paragraphes de fond, regroupés par point de l'ordre du jour.
    points: list[list[dict]] = [[]]
    titres: dict[int, str] = {}  # niveau du point → titre ; les points sont à plat dans le XML
    for el in root.iter("{*}point", "{*}paragraphe"):
        if el.tag.endswith("point"):
            points.append([])
            title = text_of(el.find("an:texte", NS))
            niveau = int(el.get("nivpoint") or 1)
            # Les points sans titre (blocs d'amendements) et les titres génériques héritent du parent.
            if title and not TITRES_IGNORES.match(title):
                titres = {n: t for n, t in titres.items() if n < niveau}
                titres[niveau] = title
            continue
        acteur = el.get("id_acteur")
        texte = text_of(el.find("an:texte", NS))
        if not acteur or not texte:
            continue  # didascalies : (Applaudissements…), (La séance est suspendue.)
        if el.get("roledebat") == "president":
            continue  # police de séance, pas de fond
        orateur = el.find("an:orateurs/an:orateur", NS)
        nom, civilite, groupe = split_orateur(text_of(orateur.find("an:nom", NS)) if orateur is not None else "")
        chemin = [titres[n] for n in sorted(titres)]
        points[-1].append(
            {
                "seance_uid": uid,
                "date": d.isoformat(),
                "date_int": int(d.strftime("%Y%m%d")),
                "section": chemin[0] if chemin else "",
                "sujet": " › ".join(chemin[1:]),
                "ordre": int(el.get("ordre_absolu_seance", 0)),
                "id_acteur": acteur,
                "orateur": nom,
                "civilite": civilite,
                "groupe": groupe,
                "qualite": text_of(orateur.find("an:qualite", NS)) if orateur is not None else "",
                "role": el.get("roledebat") or "",
                "text": texte,
                "url": f"https://www.assemblee-nationale.fr/dyn/17/comptes-rendus/seance/{uid}",
            }
        )

    # Passe 2 : on retire les interjections (A, « Très bien ! » de B, A) puis on fusionne
    # les paragraphes consécutifs d'un même orateur en une intervention.
    for paras in points:
        kept = [
            p
            for i, p in enumerate(paras)
            if not (
                len(p["text"]) < MIN_CHARS
                and 0 < i < len(paras) - 1
                and paras[i - 1]["id_acteur"] == paras[i + 1]["id_acteur"] != p["id_acteur"]
            )
        ]
        current: dict | None = None
        for p in kept:
            if current and current["id_acteur"] == p["id_acteur"]:
                current["text"] += "\n" + p["text"]
                continue
            if current and len(current["text"]) >= MIN_CHARS:
                yield current
            current = dict(p)
        if current and len(current["text"]) >= MIN_CHARS:
            yield current


def iter_interventions(limit_seances: int | None) -> Iterator[dict]:
    if not ZIP_PATH.exists():
        DATA_DIR.mkdir(exist_ok=True)
        print(f"Téléchargement {ZIP_URL}")
        urllib.request.urlretrieve(ZIP_URL, ZIP_PATH)
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = sorted(n for n in zf.namelist() if n.endswith(".xml"))
        for name in names[:limit_seances] if limit_seances else names:
            yield from parse_seance(zf.read(name))


def ensure_collection(client, dim: int, recreate: bool = False) -> None:
    if recreate and client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    if client.collection_exists(COLLECTION):
        return
    client.create_collection(COLLECTION, vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE))
    for field in ("orateur", "groupe", "id_acteur", "seance_uid"):
        client.create_payload_index(COLLECTION, field, models.PayloadSchemaType.KEYWORD)
    client.create_payload_index(COLLECTION, "date_int", models.PayloadSchemaType.INTEGER)
    client.create_payload_index(COLLECTION, "ordre", models.PayloadSchemaType.INTEGER)
    client.create_payload_index(COLLECTION, "sujet", models.PayloadSchemaType.TEXT)


def to_chunks(inter: dict) -> list[tuple[str, dict]]:
    # Contexte en tête de chunk : qui parle, de quoi — sinon « je suis contre » ne veut rien dire.
    sujet = " › ".join(t for t in (inter["section"], inter["sujet"]) if t)
    header = f"{inter['orateur']} ({inter['date']}) — {sujet}"
    return [
        (f"{header}\n{chunk}", {**inter, "chunk_index": i, "text": chunk})
        for i, chunk in enumerate(chunk_text(inter["text"]))
    ]


def index(client, items: list[tuple[str, dict]], embed_fn=embed) -> None:
    vectors = embed_fn([text for text, _ in items])
    client.upsert(
        COLLECTION,
        points=[
            models.PointStruct(
                # Id déterministe : relancer l'ingestion met à jour au lieu de dupliquer.
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{p['seance_uid']}/{p['ordre']}/{p['chunk_index']}")),
                vector=v,
                payload=p,
            )
            for v, (_, p) in zip(vectors, items, strict=True)
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-seances", type=int, help="Nombre de séances (pour tester vite)")
    parser.add_argument("--recreate", action="store_true", help="Supprime la collection avant")
    args = parser.parse_args()

    client = qdrant()
    ensure_collection(client, embedding_dim(), args.recreate)
    batch: list[tuple[str, dict]] = []
    total = 0
    for inter in iter_interventions(args.limit_seances):
        batch.extend(to_chunks(inter))
        if len(batch) >= BATCH:
            index(client, batch)
            total += len(batch)
            print(f"  {total} chunks indexés")
            batch = []
    if batch:
        index(client, batch)
        print(f"  {total + len(batch)} chunks indexés")


if __name__ == "__main__":
    main()
