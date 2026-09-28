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
            └────────────┬─────────────┘          │ vectorstore LanceDB + bge-m3     │─> data/lancedb/
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

Prérequis : [uv](https://docs.astral.sh/uv/), Node, et [Ollama](https://ollama.com/download)
avec un modèle qui sait appeler des outils (`ollama pull qwen2.5:14b` recommandé, `qwen2.5:7b` si la machine
est plus modeste).

```bash
uv sync

# Archives : téléchargées depuis Hugging Face (~900 Mo, une fois ; `uv run agora` le fait aussi au démarrage)…
uv run agora-index import
# … ou reconstruites de zéro (~2 h sur un M4 Pro)
uv run python -m agora.contexts.cinema.ingestion       # --limit 500 pour tester vite
uv run python -m agora.contexts.assemblee.ingestion    # --limit-seances 20 pour tester vite

(cd web && npm install && npm run build)
uv run agora                                           # ouvre http://127.0.0.1:8765
```

Ni Docker, ni VM, ni base à lancer : l'index est un dossier (`data/lancedb/`) ouvert directement par
l'application. Hors ligne une fois installé : bge-m3 est chargé depuis le cache local, les polices sont
embarquées dans le build, et seul Ollama (`localhost:11434`) est appelé.

Parcours : **l'Agora** (choix du modèle local) → **le Forum** (choix du guide) → **la salle** du contexte,
qui prend l'identité visuelle de son lieu.

- **Mode démo** : `AGORA_DEMO=1 uv run agora` ajoute un faux modèle instantané qui appelle vraiment les outils.
- **Front en développement** : `uv run agora --dev` + `cd web && npm run dev` (Vite, rechargement à chaud).
- **Terminal** : `uv run agora-chat cinema` ou `uv run agora-chat assemblee --model qwen2.5:7b`.

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
manifeste) est publié sur Hugging Face : [rferrat/agora-rag-index](https://huggingface.co/datasets/rferrat/agora-rag-index).
Synopsis issus de Wikipédia (CC BY-SA) ; comptes rendus de l'Assemblée nationale sous
[Licence Ouverte](https://data.assemblee-nationale.fr/licence-ouverte-open-licence).

## Développement

```bash
uv run pytest            # architecture, parseur, chunking, outils MCP et boucle agent via le protocole
uv run ruff check . && uv run ruff format --check .
```

Les tests n'ont besoin ni de bge-m3, ni d'Ollama : les outils sont appelés à travers un client MCP en mémoire,
sur une base LanceDB temporaire, avec un embedder factice et le modèle de démo.

## Feuille de route

- [x] **v0.1.0** — CLI + 2 serveurs MCP (RAG cinéma et Assemblée nationale)
- [ ] **v0.2.0** — tests, lint, CI, serveurs MCP en HTTP, ingestion complète + export d'index
- [ ] **v0.3.0** — application locale : architecture hexagonale par contextes, Ollama, identité visuelle par lieu
- [ ] **v0.4.0** — mascottes par guide, historique des conversations, regroupement des extraits par intervention
- [ ] **v0.5.0** — installation sans Docker : index embarqué (LanceDB) téléchargé au premier lancement, front précompilé
- [ ] **v0.6.0** — groupes politiques, mise à jour incrémentale des séances, nouveaux contextes
- [ ] **v0.7.0** — benchmark : qualité du retrieval (dense vs hybride), exactitude des citations, latence par modèle local

## Licence

Code sous licence [MIT](LICENSE).
