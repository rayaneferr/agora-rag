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
  - qdrant
  - embeddings
  - bge-m3
  - assemblee-nationale
  - movies
pretty_name: agora-rag — index vectoriel (films + débats de l'Assemblée nationale)
size_categories:
  - 100K<n<1M
---

# agora-rag — index vectoriel

Snapshots [Qdrant](https://qdrant.tech/) prêts à restaurer, utilisés par
[agora-rag](https://github.com/rayaneferr/agora-rag) : un agent conversationnel local dont le RAG
est exposé via MCP. L'application les télécharge et les restaure automatiquement au premier
lancement ; ils évitent environ 2 h de calcul d'embeddings.

| Fichier | Collection | Contenu |
|---|---|---|
| `films.snapshot` | `films` | ~35k synopsis de films Wikipedia, découpés en chunks (~1500 caractères) |
| `debats.snapshot` | `debats` | Comptes rendus des séances publiques de l'Assemblée nationale (17e législature), une intervention par point |
| `manifest.json` | — | Nombre de points, modèle d'embeddings, version de Qdrant, date d'export |

## Utilisation

```bash
git clone https://github.com/rayaneferr/agora-rag && cd agora-rag
uv sync
uv run agora-index import      # télécharge depuis ce dataset et restaure dans Qdrant
```

## Détails techniques

- **Embeddings** : [`BAAI/bge-m3`](https://huggingface.co/BAAI/bge-m3), 1024 dimensions, distance cosinus,
  vecteurs normalisés. Les requêtes doivent être encodées avec **le même modèle**.
- **Texte encodé** : chaque chunk est préfixé de son contexte (titre, année, genre et réalisateur pour les
  films ; orateur, date et sujet pour les débats), le payload contient le texte brut et les métadonnées.
- **Qdrant** : snapshots produits avec Qdrant 1.19 ; à restaurer avec une version égale ou supérieure.

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
