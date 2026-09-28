# agora-rag

[![CI](https://github.com/rayaneferr/agora-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/rayaneferr/agora-rag/actions/workflows/ci.yml)

Agent conversationnel dont le RAG est exposé via **MCP** : le LLM décide lui-même quand
chercher, quoi chercher et avec quels filtres, en appelant des outils de deux serveurs MCP.

```
                         ┌─> serveur MCP "cinema"    ─> Qdrant "films"   (Wikipedia Movie Plots, ~35k films)
Utilisateur ─> client ───┤     search_films, get_film
               (LiteLLM) └─> serveur MCP "assemblee" ─> Qdrant "debats"  (comptes rendus AN, 17e législature)
                               find_orateurs, search_debats, get_contexte
```

- **LLM au choix** : le client passe par LiteLLM, l'utilisateur fournit juste `--model` et sa clé.
- **Embeddings locaux** : `BAAI/bge-m3` (multilingue, 1024 dim), sur MPS si dispo.

## Démarrage

```bash
uv sync
cp .env.example .env

# Qdrant
docker compose up -d        # ou : docker run -d --name agora-qdrant -p 6333:6333 -v "$PWD/qdrant_storage:/qdrant/storage" qdrant/qdrant

# Index : téléchargé depuis Hugging Face et restauré (quelques minutes)...
uv run agora-index import
# ... ou reconstruit de zéro (~2 h sur un M4 Pro, télécharge les données brutes dans data/)
uv run python -m agora.ingestion.cinema          # --limit 500 pour tester vite
uv run python -m agora.ingestion.assemblee       # --limit-seances 20 pour tester vite
uv run agora-index export && uv run agora-index publish   # republier l'index

# Chat
uv run agora-chat --model anthropic/claude-sonnet-5
```

La clé API est lue dans cet ordre : `--api-key`, `LLM_API_KEY`, la variable standard du provider
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`…), sinon elle est demandée au lancement.

Chaque réponse affiche latence, tokens, coût et nombre d'appels d'outils.

## Serveurs MCP : stdio ou HTTP

Par défaut, `agora-chat` lance les serveurs en sous-processus (stdio). Ils peuvent aussi tourner
comme services HTTP autonomes (streamable-http, sans état) :

```bash
uv run mcp-cinema --transport http       # http://127.0.0.1:8101/mcp
uv run mcp-assemblee --transport http    # http://127.0.0.1:8102/mcp
uv run agora-chat --model openai/gpt-5.4-mini \
  --mcp-url http://127.0.0.1:8101/mcp --mcp-url http://127.0.0.1:8102/mcp
```

Ils sont indépendants du client et se branchent sur n'importe quel client MCP, par exemple Claude Code :

```bash
claude mcp add cinema -- uv --directory /chemin/vers/agora-rag run mcp-cinema
claude mcp add assemblee -- uv --directory /chemin/vers/agora-rag run mcp-assemblee
```

## Données

| Corpus | Source | Unité indexée |
|---|---|---|
| Films | [Wikipedia Movie Plots](https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries) | chunk de synopsis (~1500 car.), préfixé titre/année/genre/réalisateur |
| Débats | [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr/travaux-parlementaires/debats) (XML Syceron) | une intervention (paragraphes consécutifs d'un même orateur sous un même point), préfixée orateur/date/sujet |

L'index prêt à l'emploi (snapshots Qdrant + manifeste) est publié sur Hugging Face :
[rferrat/agora-rag-index](https://huggingface.co/datasets/rferrat/agora-rag-index).
Les données brutes ne sont pas versionnées : elles sont téléchargées par les scripts d'ingestion.
Synopsis issus de Wikipédia (CC BY-SA) ; comptes rendus de l'Assemblée nationale sous
[Licence Ouverte](https://data.assemblee-nationale.fr/licence-ouverte-open-licence).

## Développement

```bash
uv run pytest            # parseur, chunking, outils MCP testés via le protocole
uv run ruff check . && uv run ruff format --check .
```

Les tests n'ont besoin ni de Docker ni de bge-m3 : les outils sont appelés à travers un client MCP
en mémoire, avec Qdrant en mode `:memory:` et un embedder factice.

## Feuille de route

- [x] **v0.1.0** — CLI + 2 serveurs MCP (RAG cinéma et Assemblée nationale)
- [ ] **v0.2.0** — tests, lint, CI, serveurs MCP en HTTP, ingestion complète + export d'index
- [ ] **v0.3.0** — backend FastAPI (validation de clé, liste des modèles, chat en streaming)
- [ ] **v0.4.0** — front React : saisie de la clé (OpenAI / Gemini / Anthropic), chat, sources, stats
- [ ] **v0.5.0** — installation locale en une commande : Qdrant + restauration automatique du snapshot + bge-m3 + app
- [ ] **v0.6.0** — groupes politiques, historique, choix des corpus, mise à jour incrémentale des séances
- [ ] **v0.7.0** — benchmark : qualité du retrieval, exactitude des citations, latence/coût par modèle

## Licence

Code sous licence [MIT](LICENSE).
