# agora-rag

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

# Ingestion (télécharge les données dans data/)
uv run python -m agora.ingestion.cinema          # --limit 500 pour tester vite
uv run python -m agora.ingestion.assemblee       # --limit-seances 20 pour tester vite

# Chat
uv run agora-chat --model anthropic/claude-sonnet-5
```

La clé API est lue dans cet ordre : `--api-key`, `LLM_API_KEY`, la variable standard du provider
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`…), sinon elle est demandée au lancement.

Chaque réponse affiche latence, tokens, coût et nombre d'appels d'outils.

## Utiliser les serveurs depuis un autre client MCP

Les serveurs sont indépendants du client (stdio). Exemple pour Claude Code :

```bash
claude mcp add cinema -- uv --directory /chemin/vers/agora-rag run mcp-cinema
claude mcp add assemblee -- uv --directory /chemin/vers/agora-rag run mcp-assemblee
```

## Données

| Corpus | Source | Unité indexée |
|---|---|---|
| Films | [Wikipedia Movie Plots](https://huggingface.co/datasets/vishnupriyavr/wiki-movie-plots-with-summaries) | chunk de synopsis (~1500 car.), préfixé titre/année/genre/réalisateur |
| Débats | [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr/travaux-parlementaires/debats) (XML Syceron) | une intervention (paragraphes consécutifs d'un même orateur sous un même point), préfixée orateur/date/sujet |

Les données ne sont pas versionnées : elles sont téléchargées par les scripts d'ingestion.
Synopsis issus de Wikipédia (CC BY-SA) ; comptes rendus de l'Assemblée nationale sous
[Licence Ouverte](https://data.assemblee-nationale.fr/licence-ouverte-open-licence).

## Feuille de route

- [x] **v0.1.0** — CLI + 2 serveurs MCP (RAG cinéma et Assemblée nationale)
- [ ] **v0.2.0** — tests, lint, CI, serveurs MCP en HTTP, ingestion complète + export d'index
- [ ] **v0.3.0** — backend FastAPI (validation de clé, liste des modèles, chat en streaming)
- [ ] **v0.4.0** — front React : saisie de la clé (OpenAI / Gemini / Anthropic), chat, sources, stats
- [ ] **v0.5.0** — déploiement `docker compose` complet + démo hébergée
- [ ] **v0.6.0** — groupes politiques, historique, choix des corpus
- [ ] **v0.7.0** — benchmark : qualité du retrieval, exactitude des citations, latence/coût par modèle

## Licence

Code sous licence [MIT](LICENSE).
