---
license: other
license_name: mixed-cc-by-sa-4.0-and-licence-ouverte-2011
license_link: https://huggingface.co/datasets/rferrat/agora-rag-index#licences
language:
  - fr
  - en
tags:
  - rag
  - mcp
  - lancedb
  - embeddings
  - bge-m3
  - assemblee-nationale
  - movies
pretty_name: agora-rag — index vectoriel (films + débats de l'Assemblée nationale)
size_categories:
  - 100K<n<1M
---

# agora-rag — index vectoriel

Tables [LanceDB](https://lancedb.com/) prêtes à l'emploi, utilisées par
[agora-rag](https://github.com/rayaneferr/agora-rag) : des serveurs MCP de recherche sémantique à brancher sur
Claude. LanceDB est une base embarquée : les serveurs ouvrent ces dossiers directement, sans serveur ni
restauration. Ils évitent environ 2 h de calcul d'embeddings.

| Chemin | Table | Contenu |
|---|---|---|
| `lancedb/films.lance/` | `films` | ~35k synopsis de films Wikipedia, découpés en chunks (~1500 caractères) |
| `lancedb/debats.lance/` | `debats` | Comptes rendus des séances publiques de l'Assemblée nationale (17e législature), une intervention par point |
| `manifest.json` | — | Nombre de lignes, modèle d'embeddings, version de LanceDB, date d'export |

## Utilisation

```bash
git clone https://github.com/rayaneferr/agora-rag && cd agora-rag
uv sync
uv run agora-index import      # télécharge les tables dans data/lancedb/ et vérifie leurs empreintes
```

agora-rag épingle un commit précis de ce dataset et compare chaque fichier téléchargé aux empreintes
publiées par le Hub pour ce commit (sha256 des fichiers LFS). Une nouvelle publication n'est utilisée qu'après
mise à jour de la révision dans le code d'agora-rag. Le `manifest.json` contient aussi le sha256 de chaque
fichier de table.

## Détails techniques

- **Embeddings** : [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3), 1024 dimensions, distance cosinus,
  vecteurs normalisés. Les requêtes doivent être encodées avec **le même modèle**.
- **Texte encodé** : chaque chunk est préfixé de son contexte (titre, année, genre et réalisateur pour les
  films ; orateur, date et sujet pour les débats) ; les colonnes contiennent le texte brut et les métadonnées.
- **Lecture directe** : `lancedb.connect("lancedb").open_table("films")`, ou tout lecteur du format Lance.

## Provenance et licences

Ce dataset redistribue des textes issus de deux sources, chacune sous sa propre licence. Chaque ligne garde le
lien vers son document d'origine (`wiki_url` pour les films, `url` pour les séances).

### Films : table `films`, CC BY-SA 4.0

- **Origine** : sections « Plot » d'articles de films de [Wikipédia en anglais](https://en.wikipedia.org/),
  écrites par ses contributeurs.
- **Chaîne de collecte** : [Wikipedia Movie Plots](https://www.kaggle.com/datasets/jrobischon/wikipedia-movie-plots)
  (JustinR, Kaggle, 2018, 34 886 films) → [Wikipedia Movie Plots with AI Plot Summaries](https://www.kaggle.com/datasets/gabrieltardochi/wikipedia-movie-plots-with-plot-summaries)
  (Gabriel Tardochi, 2021, ajout de résumés) → miroir
  [vishnupriyavr/wiki-movie-plots-with-summaries](https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries),
  téléchargé par agora-rag.
- **Licence** : [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), celle des textes de Wikipédia et
  du dataset source. La table `films` est une adaptation (découpage en chunks, métadonnées nettoyées, embeddings)
  distribuée **sous la même licence** ; toute réutilisation doit citer Wikipédia et ses contributeurs, indiquer
  la licence et partager ses adaptations dans les mêmes conditions.
- **Résumés** : la colonne `summary` a été générée automatiquement par le modèle
  [DistilBART-CNN-12-6](https://huggingface.co/sshleifer/distilbart-cnn-12-6) dans le dataset source. Elle
  peut contenir des erreurs ; le texte de référence est le synopsis (`text`).

### Débats : table `debats`, Licence Ouverte

- **Origine** : comptes rendus intégraux des séances publiques de l'Assemblée nationale, 17e législature,
  publiés au format XML Syceron sur [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr/travaux-parlementaires/debats).
- **Producteur** : Assemblée nationale.
- **Licence** : [Licence Ouverte / Open Licence](https://data.assemblee-nationale.fr/licence-ouverte-open-licence)
  d'Etalab, dans la version d'octobre 2011 publiée par l'Assemblée. Réutilisation libre, y compris commerciale,
  à condition de mentionner la source (« Assemblée nationale ») et la date de dernière mise à jour des données.
- **Date des données** : séances du 18 juillet 2024 au 21 juillet 2026 ; export de l'index : voir `exported_at`
  dans `manifest.json`.
- **Transformations** : interventions reconstituées (paragraphes consécutifs d'un même orateur), noms d'orateurs
  normalisés, interjections écartées, découpage en chunks et embeddings. Le texte des interventions n'est pas
  modifié.

### Modèle et code

Embeddings calculés avec [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3) (licence MIT). Le code qui produit
cet index est sous licence MIT : https://github.com/rayaneferr/agora-rag
