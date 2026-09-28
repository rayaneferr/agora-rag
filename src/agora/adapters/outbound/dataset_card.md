---
license: other
license_name: mixed-cc-by-sa-4.0-and-licence-ouverte-2.0
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
[agora-rag](https://github.com/rayaneferr/agora-rag) : un agent conversationnel local dont le RAG
est exposé via MCP. LanceDB est une base embarquée : l'application télécharge ces dossiers au premier
lancement et les ouvre directement, sans serveur ni restauration. Ils évitent environ 2 h de calcul
d'embeddings.

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

L'application épingle un commit précis de ce dataset et compare chaque fichier téléchargé aux empreintes
publiées par le Hub pour ce commit (sha256 des fichiers LFS). Une nouvelle publication n'est utilisée qu'après
mise à jour de la révision dans le code d'agora-rag. Le `manifest.json` contient aussi le sha256 de chaque
fichier de table.

## Détails techniques

- **Embeddings** : [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3), 1024 dimensions, distance cosinus,
  vecteurs normalisés. Les requêtes doivent être encodées avec **le même modèle**.
- **Texte encodé** : chaque chunk est préfixé de son contexte (titre, année, genre et réalisateur pour les
  films ; orateur, date et sujet pour les débats) ; les colonnes contiennent le texte brut et les métadonnées.
- **Lecture directe** : `lancedb.connect("lancedb").open_table("films")`, ou tout lecteur du format Lance.

## Licences

Ce dataset redistribue des textes issus de deux sources, chacune sous sa propre licence :

- **Films** : synopsis issus de Wikipédia via
  [vishnupriyavr/wiki-movie-plots-with-summaries](https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries)
  (lui-même issu du dataset Kaggle *Wikipedia Movie Plots*), sous licence
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). La collection `films` est distribuée
  sous la même licence. Les résumés courts (`summary`) de ce dataset source ont été générés par IA.
- **Débats** : comptes rendus de l'Assemblée nationale,
  [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr/travaux-parlementaires/debats), sous
  [Licence Ouverte / Open Licence](https://data.assemblee-nationale.fr/licence-ouverte-open-licence).
  Source : Assemblée nationale ; date de dernière mise à jour des données : voir `exported_at` dans
  `manifest.json`.

Le code qui produit cet index est sous licence MIT : https://github.com/rayaneferr/agora-rag
