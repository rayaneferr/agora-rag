"""Ingestion de Wikipedia Movie Plots (~35k films) dans la collection Qdrant `films`.

uv run python -m agora.ingestion.cinema [--limit 500]
"""

import argparse
import urllib.request

import polars as pl
from qdrant_client import models

from agora.common import COLLECTION_FILMS, DATA_DIR, chunk_text, embed, embedding_dim, qdrant

CSV_URL = (
    "https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries/"
    "resolve/main/wiki_movie_plots_deduped_with_summaries.csv"
)
CSV_PATH = DATA_DIR / "wiki_movie_plots.csv"
BATCH = 256


def load_films(limit: int | None) -> pl.DataFrame:
    if not CSV_PATH.exists():
        DATA_DIR.mkdir(exist_ok=True)
        print(f"Téléchargement {CSV_URL}")
        urllib.request.urlretrieve(CSV_URL, CSV_PATH)
    df = pl.read_csv(CSV_PATH, infer_schema_length=0).with_row_index("film_id")
    return df.head(limit) if limit else df


def clean(value: str | None) -> str | None:
    return None if value is None or value.strip().lower() in {"", "unknown", "null"} else value.strip()


def build_points(df: pl.DataFrame) -> list[tuple[str, dict]]:
    points = []
    for row in df.iter_rows(named=True):
        meta = {
            "film_id": int(row["film_id"]),
            "title": row["Title"],
            "year": int(row["Release Year"]),
            "origin": clean(row["Origin/Ethnicity"]),
            "director": clean(row["Director"]),
            "cast": clean(row["Cast"]),
            "genre": clean(row["Genre"]),
            "wiki_url": row["Wiki Page"],
            "summary": clean(row["PlotSummary"]),
        }
        header = f"{meta['title']} ({meta['year']}) — genre: {meta['genre'] or '?'}, réalisé par {meta['director'] or '?'}"
        for i, chunk in enumerate(chunk_text(row["Plot"] or "")):
            # Le titre est répété dans chaque chunk pour que l'embedding reste ancré au film.
            points.append((f"{header}\n{chunk}", {**meta, "chunk_index": i, "text": chunk}))
    return points


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Nombre de films (pour tester vite)")
    parser.add_argument("--recreate", action="store_true", help="Supprime la collection avant")
    args = parser.parse_args()

    client = qdrant()
    if args.recreate and client.collection_exists(COLLECTION_FILMS):
        client.delete_collection(COLLECTION_FILMS)
    if not client.collection_exists(COLLECTION_FILMS):
        client.create_collection(
            COLLECTION_FILMS,
            vectors_config=models.VectorParams(size=embedding_dim(), distance=models.Distance.COSINE),
        )
        client.create_payload_index(COLLECTION_FILMS, "film_id", models.PayloadSchemaType.INTEGER)
        client.create_payload_index(COLLECTION_FILMS, "year", models.PayloadSchemaType.INTEGER)
        for field in ("genre", "director", "cast", "title"):
            client.create_payload_index(COLLECTION_FILMS, field, models.PayloadSchemaType.TEXT)

    points = build_points(load_films(args.limit))
    print(f"{len(points)} chunks à indexer")
    for start in range(0, len(points), BATCH):
        batch = points[start : start + BATCH]
        vectors = embed([text for text, _ in batch])
        client.upsert(
            COLLECTION_FILMS,
            points=[
                models.PointStruct(id=start + i, vector=vec, payload=payload)
                for i, (vec, (_, payload)) in enumerate(zip(vectors, batch))
            ],
        )
        print(f"  {min(start + BATCH, len(points))}/{len(points)}")


if __name__ == "__main__":
    main()
