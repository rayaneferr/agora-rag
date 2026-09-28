# Agora

[![CI](https://github.com/rayaneferr/agora-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/rayaneferr/agora-rag/actions/workflows/ci.yml)
[![Licence MIT](https://img.shields.io/badge/licence-MIT-black)](LICENSE)
[![Index Hugging Face](https://img.shields.io/badge/index-Hugging%20Face-ffcc4d)](https://huggingface.co/datasets/rferrat/agora-rag-index)

> *Local RAG agents exposed through MCP: film synopses and French National Assembly debates. Runs fully offline with
> Ollama, LanceDB, FastAPI and React. No API key.*

**La place où l'on vient chercher.** Agora réunit des agents conversationnels spécialisés, chacun dans
son propre **contexte** : une base indexée, un serveur **MCP** qui l'expose en outils, et une identité.
Tout tourne en local, avec un modèle [Ollama](https://ollama.com) : gratuit, hors ligne, rien ne sort
de la machine.

![L'Hémicycle : question sur la dette publique, appel MCP déplié, réponse sourcée](docs/screenshot-hemicycle.png)

| Lieu | Guide | Archives | Outils MCP |
|---|---|---|---|
| **La Salle obscure** | Lumière | ~35 000 synopsis de films (Wikipédia), sortis de 1901 à 2017 | `search_films`, `get_film` |
| **L'Hémicycle** | L'Huissier | 601 séances de l'Assemblée nationale (17e législature, juillet 2024 → juillet 2026) | `find_orateurs`, `search_debats`, `get_contexte` |

Le modèle décide lui-même quand chercher, quoi chercher et avec quels filtres ; chaque réponse cite
ses sources (fiche Wikipédia, compte rendu de séance), et l'interface montre en direct les appels
d'outils, le journal technique et la latence. L'étendue exacte des archives est calculée depuis l'index,
affichée dans l'interface et donnée au modèle : il sait jusqu'où vont ses archives.

## Architecture hexagonale

```
                 adaptateurs entrants                    adaptateurs sortants
            ┌──────────────────────────┐          ┌──────────────────────────────────┐
navigateur ─┤ api.py (FastAPI, SSE)    │          │ llm.py      Ollama (API native)  │─> Ollama
terminal ───┤ cli.py                   │          │ mcp.py      passerelle MCP       │─> serveur MCP du contexte
            └────────────┬─────────────┘          │ vectorstore LanceDB + bge-m3     │─> data/lancedb/
                         ▼                        │ index_hub   index ↔ Hugging Face │─> dataset épinglé
                ┌─────────────────────────────────┴───────────────────────────────────┐
                │ core/   agent.py (boucle agent, événements)                         │
                │         ports.py (LLMPort, ToolGateway)                             │
                │         context.py (ContextSpec) · text.py                          │
                └─────────────────────────────────────────────────────────────────────┘
contexts/cinema/     __init__ (identité, prompt, sources) · server.py (MCP) · ingestion.py
contexts/assemblee/  idem
```

- **Le cœur ne dépend de rien** : il reçoit un modèle (`LLMPort`) et des outils (`ToolGateway`) par ses
  ports. Un test (`tests/test_architecture.py`) échoue si le cœur importe un adaptateur ou un contexte.
- **Un contexte = un dossier** : identité (lieu, guide, thème), prompt système, serveur MCP, ingestion,
  et la façon de transformer les résultats d'outils en sources citables. Ajouter un domaine (sport, droit…)
  revient à créer `contexts/<nom>/` et à l'inscrire dans `contexts/__init__.py`.
- **Chaque agent ne voit que ses outils** : une passerelle MCP par contexte.
- **Ollama est appelé directement** (`/api/chat`, streaming, appels d'outils natifs) : pas de SDK
  intermédiaire, une centaine de paquets en moins.

## Démarrage

Prérequis : [uv](https://docs.astral.sh/uv/), Node, et [Ollama](https://ollama.com/download)
avec un modèle qui sait appeler des outils (`ollama pull qwen2.5:14b` recommandé, environ 10 Go de RAM ;
`qwen2.5:7b` si la machine est plus modeste).

```bash
uv sync
(cd web && npm install && npm run build)
uv run agora                                           # ouvre http://127.0.0.1:8765
```

Au premier lancement, l'application télécharge l'index (~890 Mo) et le modèle d'embeddings bge-m3 (~2,3 Go)
depuis Hugging Face, **en affichant la progression dans l'interface** ; la saisie s'ouvre quand tout est prêt.
Ensuite, tout fonctionne hors ligne : seul Ollama (`localhost:11434`) est appelé. Compter environ 5 Go de disque
au total, environnement Python compris.

Pour préparer les données à l'avance ou les reconstruire :

```bash
uv run agora-index import                              # index + bge-m3, avec vérification des empreintes
uv run agora-index verify                              # compare data/lancedb/ à la révision épinglée
uv run python -m agora.contexts.cinema.ingestion       # reconstruction (~2 h sur un M4 Pro) ; --limit 500 pour tester
uv run python -m agora.contexts.assemblee.ingestion    # --limit-seances 20 pour tester vite
```

Ni Docker, ni VM, ni base à lancer : l'index est un dossier (`data/lancedb/`, ou `$AGORA_HOME/lancedb`)
ouvert directement par l'application.

Parcours : **l'Agora** (choix du modèle local) → **le Forum** (choix du guide) → **la salle** du contexte,
qui prend l'identité visuelle de son lieu.

- **Mode démo** : `AGORA_DEMO=1 uv run agora` ajoute un faux modèle instantané qui appelle vraiment les outils.
- **Front en développement** : `uv run agora --dev` + `cd web && npm run dev` (Vite, rechargement à chaud).
- **Terminal** : `uv run agora-chat cinema` ou `uv run agora-chat assemblee --model qwen2.5:7b`.

![La Salle obscure en thème sombre : recherche dans les synopsis, sources Wikipédia](docs/screenshot-salle-obscure.png)

## Pourquoi LanceDB plutôt qu'un serveur vectoriel

La première version stockait l'index dans Qdrant. C'est une très bonne base, mais c'est un **serveur** : sur Mac
et Windows, il tourne dans Docker, donc dans une machine virtuelle Linux. Pour une application personnelle qui
doit s'installer par `git clone` + `uv sync`, c'était le prérequis le plus lourd.

LanceDB est **embarqué**, comme SQLite : une bibliothèque Python qui lit un dossier de fichiers (format colonnaire
Lance). Conséquences mesurées sur ce corpus (187 000 chunks, 1024 dimensions, M4 Pro) :

| | Qdrant 1.19 (Docker) | LanceDB 0.39 (embarqué) |
|---|---|---|
| Prérequis | Docker + VM | aucun (`uv sync`) |
| Index distribué | snapshots, 1,19 Go, à restaurer | dossiers, 0,87 Go, ouverts tels quels |
| Recherche films (sans filtre) | HNSW approché | exacte, ~50 ms |
| Recherche filtrée (orateur, genre, dates) | filtre pendant le parcours | pré-filtre SQL, 60 à 250 ms |

La recherche est exhaustive (pas d'index ANN) : à cette taille elle reste sous le quart de seconde et ne manque
aucun voisin. Comparé à Qdrant sur quatre requêtes, le top 5 est identique partout ; sur le top 20 des films,
l'index HNSW de Qdrant ne retrouvait que 16 à 17 des 20 vrais plus proches voisins, contre 20/20 ici. Les filtres
que le modèle passe aux outils sont échappés avant d'entrer dans la clause SQL (`tests/test_servers.py`).

## Sécurité et intégrité

Une application locale qui télécharge des fichiers et ouvre un port mérite quelques garde-fous :

- **Index et modèle épinglés.** Le code fixe un commit du dataset Hugging Face et un commit de bge-m3. Chaque
  fichier téléchargé est comparé aux empreintes publiées par le Hub pour ce commit (sha256 des fichiers LFS,
  sha1 git des autres) ; un fichier remplacé ou tronqué est refusé. Les poids PyTorch étant du pickle, seule la
  révision validée est chargée.
- **Boucle locale seulement.** L'API écoute sur 127.0.0.1 et refuse toute requête dont l'en-tête `Host` ne la
  désigne pas (protection contre le DNS rebinding : un site tiers ne peut pas piloter l'agent). Les serveurs MCP
  en HTTP refusent une adresse d'écoute non locale sans `--allow-remote`, car ils n'ont pas d'authentification.
- **Données externes traitées comme telles.** Le XML de l'Assemblée est parsé sans résolution d'entités ni accès
  réseau ; les filtres SQL sont échappés ; le Markdown du modèle est rendu sans HTML brut.
- **Chaîne d'intégration.** Actions GitHub épinglées par SHA, jeton en lecture seule, Dependabot sur les trois
  écosystèmes (uv, npm, actions), audits `pip-audit` et `npm audit` propres à la date de publication.

## Serveurs MCP : stdio ou HTTP

Par défaut, l'application lance chaque serveur en sous-processus (stdio). Ils tournent aussi comme services
HTTP autonomes (streamable-http, sans état) et se branchent sur n'importe quel client MCP :

```bash
uv run mcp-cinema --transport http       # http://127.0.0.1:8101/mcp
uv run mcp-assemblee --transport http    # http://127.0.0.1:8102/mcp
uv run agora-chat cinema --mcp-url http://127.0.0.1:8101/mcp

claude mcp add cinema -- uv --directory /chemin/vers/agora-rag run mcp-cinema   # ex. Claude Code
```

## Données

| Contexte | Source | Unité indexée |
|---|---|---|
| Cinéma | [Wikipedia Movie Plots](https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries) | chunk de synopsis (~1500 car.), préfixé titre/année/genre/réalisateur |
| Assemblée | [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr/travaux-parlementaires/debats) (XML Syceron) | une intervention (paragraphes consécutifs d'un même orateur sous un même point), préfixée orateur/date/sujet |

Embeddings locaux `BAAI/bge-m3` (multilingue, 1024 dim). L'index prêt à l'emploi (tables LanceDB +
manifeste avec empreintes) est publié sur Hugging Face : [rferrat/agora-rag-index](https://huggingface.co/datasets/rferrat/agora-rag-index).
Synopsis issus de Wikipédia (CC BY-SA) ; comptes rendus de l'Assemblée nationale sous
[Licence Ouverte](https://data.assemblee-nationale.fr/licence-ouverte-open-licence).

## Développement

```bash
uv run pytest                                     # architecture, parseur, outils MCP, boucle agent, API HTTP, intégrité
uv run ruff check . && uv run ruff format --check .
(cd web && npm run lint && npm test)              # Biome (lint + format) et Vitest (état de conversation, parseur SSE)
```

Les tests n'ont besoin ni de bge-m3, ni d'Ollama, ni de l'index : les outils sont appelés à travers un client
MCP en mémoire, sur une base LanceDB temporaire, avec un embedder factice et le modèle de démo.

## Feuille de route

- [x] **v0.1.0** — CLI + 2 serveurs MCP (RAG cinéma et Assemblée nationale)
- [x] **v0.2** — tests, lint, CI, serveurs MCP en HTTP, ingestion complète + export d'index
- [x] **v0.3** — application locale : architecture hexagonale par contextes, Ollama, sans clé API
- [x] **v0.4** — installation sans Docker : index embarqué (LanceDB) publié sur Hugging Face, 100 % hors ligne
- [x] **v0.5.0** — interface épurée : recherches MCP repliables, sources compactes, thème clair/sombre
- [x] **v0.5.1** — audit : index épinglé et vérifié, Host validé, premier lancement visible, Ollama natif, Biome + Vitest
- [ ] **v0.6.0** — historique des conversations, regroupement des extraits par intervention
- [ ] **v0.7.0** — groupes politiques, mise à jour incrémentale des séances, nouveaux contextes
- [ ] **v0.8.0** — benchmark : qualité du retrieval (dense vs hybride, bge-m3 via Ollama vs PyTorch), exactitude des citations, latence par modèle local

## Licence

Code sous licence [MIT](LICENSE).
