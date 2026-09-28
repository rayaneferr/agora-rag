"""Ingestion de Wikipedia Movie Plots (~35k films) dans la table LanceDB `films`.

uv run python -m agora.contexts.cinema.ingestion [--limit 500]
"""

import argparse
import urllib.request

import polars as pl
import pyarrow as pa

from agora.adapters.outbound import vectorstore as vs
from agora.contexts.cinema import COLLECTION
from agora.core.text import chunk_text

CSV_URL = (
    "https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries/"
    "resolve/main/wiki_movie_plots_deduped_with_summaries.csv"
)
CSV_PATH = vs.DATA_DIR / "wiki_movie_plots.csv"
BATCH = 256


def load_films(limit: int | None) -> pl.DataFrame:
    if not CSV_PATH.exists():
        vs.DATA_DIR.mkdir(exist_ok=True)
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
        header = (
            f"{meta['title']} ({meta['year']}) — genre: {meta['genre'] or '?'}, réalisé par {meta['director'] or '?'}"
        )
        for i, chunk in enumerate(chunk_text(row["Plot"] or "")):
            # Le titre est répété dans chaque chunk pour que l'embedding reste ancré au film.
            points.append((f"{header}\n{chunk}", {**meta, "chunk_index": i, "text": chunk}))
    return points


def schema(dim: int) -> pa.Schema:
    text = pa.string()
    return pa.schema(
        [
            pa.field("id", pa.int64()),
            pa.field("film_id", pa.int64()),
            pa.field("title", text),
            pa.field("year", pa.int32()),
            *(pa.field(f, text) for f in ("origin", "director", "cast", "genre", "wiki_url", "summary")),
            pa.field("chunk_index", pa.int32()),
            pa.field("text", text),
            vs.vector_field(dim),
        ]
    )


def ensure_table(dim: int, recreate: bool = False) -> None:
    vs.ensure_table(COLLECTION, schema(dim), recreate)


def index(items: list[tuple[str, dict]], embed_fn=None) -> None:
    vectors = (embed_fn or vs.embed)([text for text, _ in items])
    rows = [
        {**p, "id": p["film_id"] * 1000 + p["chunk_index"], "vector": v}
        for v, (_, p) in zip(vectors, items, strict=True)
    ]
    vs.upsert(COLLECTION, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Nombre de films (pour tester vite)")
    parser.add_argument("--recreate", action="store_true", help="Supprime la table avant")
    args = parser.parse_args()

    ensure_table(vs.embedding_dim(), args.recreate)
    points = build_points(load_films(args.limit))
    print(f"{len(points)} chunks à indexer")
    for start in range(0, len(points), BATCH):
        index(points[start : start + BATCH])
        print(f"  {min(start + BATCH, len(points))}/{len(points)}")


if __name__ == "__main__":
    main()
