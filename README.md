# Agora

[![CI](https://github.com/rayaneferr/agora-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/rayaneferr/agora-rag/actions/workflows/ci.yml)

**La place où l'on vient chercher.** Agora réunit des agents conversationnels spécialisés, chacun dans
son propre **contexte** : une base indexée, un serveur **MCP** qui l'expose en outils, et une identité.
Tout tourne en local, avec un modèle [Ollama](https://ollama.com) : gratuit, hors ligne, rien ne sort
de la machine.

| Lieu | Guide | Archives | Outils MCP |
|---|---|---|---|
| **La Salle obscure** | Lumière | ~35 000 synopsis de films (Wikipédia) | `search_films`, `get_film` |
| **L'Hémicycle** | L'Huissier | 601 séances de l'Assemblée nationale (17e législature) | `find_orateurs`, `search_debats`, `get_contexte` |

Le modèle décide lui-même quand chercher, quoi chercher et avec quels filtres ; chaque réponse cite
ses sources (fiche Wikipédia, compte rendu de séance), et l'interface montre en direct les appels
d'outils, le journal technique et la latence.

## Architecture hexagonale

```
                 adaptateurs entrants                    adaptateurs sortants
            ┌──────────────────────────┐          ┌──────────────────────────────────┐
navigateur ─┤ api.py (FastAPI, SSE)    │          │ llm.py      Ollama · démo        │─> Ollama
terminal ───┤ cli.py                   │          │ mcp.py      passerelle MCP       │─> serveur MCP du contexte
            └────────────┬─────────────┘          │ vectorstore Qdrant + bge-m3      │─> Qdrant
                         ▼                        └──────────────▲───────────────────┘
                ┌─────────────────────────────────────────────────┴───┐
                │ core/   agent.py (boucle agent, événements)         │
                │         ports.py (LLMPort, ToolGateway)             │
                │         context.py (ContextSpec) · text.py          │
                └─────────────────────────────────────────────────────┘
contexts/cinema/     __init__ (identité, prompt, sources) · server.py (MCP) · ingestion.py
contexts/assemblee/  idem
```

- **Le cœur ne dépend de rien** : il reçoit un modèle (`LLMPort`) et des outils (`ToolGateway`) par ses
  ports. Un test (`tests/test_architecture.py`) échoue si le cœur importe un adaptateur ou un contexte.
- **Un contexte = un dossier** : identité (lieu, guide, thème), prompt système, serveur MCP, ingestion,
  et la façon de transformer les résultats d'outils en sources citables. Ajouter un domaine (sport, droit…)
  revient à créer `contexts/<nom>/` et à l'inscrire dans `contexts/__init__.py`.
- **Chaque agent ne voit que ses outils** : une passerelle MCP par contexte.

## Démarrage

Prérequis : [uv](https://docs.astral.sh/uv/), Docker, Node, et [Ollama](https://ollama.com/download)
avec un modèle qui sait appeler des outils (`ollama pull qwen2.5:14b` recommandé, `qwen2.5:7b` si la machine
est plus modeste).

```bash
uv sync
docker run -d --name agora-qdrant -p 6333:6333 -v "$PWD/qdrant_storage:/qdrant/storage" qdrant/qdrant

# Archives : téléchargées depuis Hugging Face et restaurées (quelques minutes)…
uv run agora-index import
# … ou reconstruites de zéro (~2 h sur un M4 Pro)
uv run python -m agora.contexts.cinema.ingestion       # --limit 500 pour tester vite
uv run python -m agora.contexts.assemblee.ingestion    # --limit-seances 20 pour tester vite

(cd web && npm install && npm run build)
uv run agora                                           # ouvre http://127.0.0.1:8765
```

Parcours : **l'Agora** (choix du modèle local) → **le Forum** (choix du guide) → **la salle** du contexte,
qui prend l'identité visuelle de son lieu.

- **Mode démo** : `AGORA_DEMO=1 uv run agora` ajoute un faux modèle instantané qui appelle vraiment les outils.
- **Front en développement** : `uv run agora --dev` + `cd web && npm run dev` (Vite, rechargement à chaud).
- **Terminal** : `uv run agora-chat cinema` ou `uv run agora-chat assemblee --model qwen2.5:7b`.

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

Embeddings locaux `BAAI/bge-m3` (multilingue, 1024 dim). L'index prêt à l'emploi (snapshots Qdrant +
manifeste) est publié sur Hugging Face : [rferrat/agora-rag-index](https://huggingface.co/datasets/rferrat/agora-rag-index).
Synopsis issus de Wikipédia (CC BY-SA) ; comptes rendus de l'Assemblée nationale sous
[Licence Ouverte](https://data.assemblee-nationale.fr/licence-ouverte-open-licence).

## Développement

```bash
uv run pytest            # architecture, parseur, chunking, outils MCP et boucle agent via le protocole
uv run ruff check . && uv run ruff format --check .
```

Les tests n'ont besoin ni de Docker, ni de bge-m3, ni d'Ollama : les outils sont appelés à travers un client
MCP en mémoire, avec Qdrant en mode `:memory:`, un embedder factice et le modèle de démo.

## Feuille de route

- [x] **v0.1.0** — CLI + 2 serveurs MCP (RAG cinéma et Assemblée nationale)
- [ ] **v0.2.0** — tests, lint, CI, serveurs MCP en HTTP, ingestion complète + export d'index
- [ ] **v0.3.0** — application locale : architecture hexagonale par contextes, Ollama, identité visuelle par lieu
- [ ] **v0.4.0** — mascottes par guide, historique des conversations, regroupement des extraits par intervention
- [ ] **v0.5.0** — installation locale en une commande : Qdrant + restauration automatique du snapshot + app
- [ ] **v0.6.0** — groupes politiques, mise à jour incrémentale des séances, nouveaux contextes
- [ ] **v0.7.0** — benchmark : qualité du retrieval (dense vs hybride), exactitude des citations, latence par modèle local

## Licence

Code sous licence [MIT](LICENSE).
