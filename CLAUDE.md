# CLAUDE.md — agora-rag

Serveurs MCP de RAG sémantique (bge-m3 + LanceDB) sur deux corpus — débats de l'Assemblée nationale, synopsis de
films — destinés à être branchés sur Claude, plus une application locale optionnelle (FastAPI + React + Ollama).
Le README raconte l'évolution du projet et justifie les choix : le lire avant de proposer un changement de cap.

## Commandes

```bash
uv sync                                   # dépendances (torch CPU sous Linux, cf. [tool.uv.sources])
uv run agora-index import                 # index (~890 Mo) + bge-m3 (~2,3 Go) → data/ et cache HF, empreintes vérifiées
uv run pytest                             # rapide (~2 s) : ni bge-m3, ni index, ni Ollama
uv run ruff check . && uv run ruff format --check .
(cd web && npm run lint && npm test && npm run build)

uv run mcp-assemblee | mcp-cinema         # un serveur MCP en stdio (--transport http pour le servir en HTTP)
uv run agora-mcp-public                   # tous les contextes sur :8100 (/<contexte>/mcp, /health)
uv run python scripts/smoke_test.py       # vérifie agora-mcp-public avec l'index réel (à lancer avant un déploiement)
uv run agora                              # application locale (nécessite Ollama et web/dist)
```

La CI (`.github/workflows/ci.yml`) lance exactement ruff, pytest, Biome, Vitest et le build du front.

## Architecture (hexagonale, par contextes)

- `src/agora/core/` : boucle agent, ports (`LLMPort`, `ToolGateway`), `ContextSpec`. **N'importe que la bibliothèque
  standard et lui-même** — `tests/test_architecture.py` le vérifie (liste `STDLIB_OK`).
- `src/agora/contexts/<nom>/` : `__init__.py` (le `SPEC` : identité, prompt système, sources), `server.py` (outils,
  prompts et resource MCP), `ingestion.py`. **Un contexte n'importe jamais un autre contexte** (testé aussi).
  Nouveau contexte = nouveau dossier + inscription dans `contexts/__init__.py` ; il est alors exposé partout.
- `src/agora/adapters/inbound/` : `api.py` (app locale), `cli.py`, `mcp_public.py` (tous les contextes, un port).
- `src/agora/adapters/outbound/` : `vectorstore.py` (LanceDB + bge-m3), `mcp_serve.py` (lancement stdio/HTTP,
  `archives()`, `guided_prompt()`), `mcp.py` (passerelle client), `llm.py` (Ollama, démo), `index_hub.py`.

## Invariants à ne pas casser

- **Révisions épinglées** : `INDEX_REVISION` (index_hub.py) et `EMBED_REVISION` (vectorstore.py). Tout fichier
  téléchargé est vérifié contre les empreintes du Hub. Ne jamais charger bge-m3 sans révision (poids = pickle).
- **Filtres SQL** : toute valeur venant du modèle passe par `vs.quote()` ou `int()` avant d'entrer dans un `where`.
- **Exposition réseau** : écoute non locale seulement avec `--allow-remote` ; l'API locale valide `Host`.
  `mcp_public.py` : hôtes/origines autorisés, corps ≤ 64 Ko, débit par IP, pas de journal d'accès.
- **Prompts MCP ≠ prompts système** : les prompts système (dans `SPEC`) imposent un périmètre propre à l'application ;
  les prompts MCP (`RULES` dans chaque `server.py`) portent des règles de sourçage pour l'assistant de l'utilisateur.
- **L'étendue des archives** est toujours calculée depuis l'index (`ContextSpec.coverage_text`), jamais écrite en dur.

## Pièges connus

- Starlette ne lance pas le `lifespan` des apps montées : `mcp_public.py` démarre lui-même chaque
  `session_manager` ; sans ça, toutes les requêtes MCP échouent.
- bge-m3 se charge en tâche de fond (`warm_up`, ~20 s) : `/health` répond 503 `starting` tant qu'il n'est pas prêt.
- Les tests remplacent `vs.embed` par un embedder factice et `vs.DB_DIR` par un dossier temporaire (`conftest.py`) ;
  tester les outils **à travers le protocole MCP** (client en mémoire), pas en appel Python direct.
- Les synopsis sont en anglais : les requêtes `search_films` en anglais donnent de meilleurs résultats.

## Déploiement

Prêt mais **non actif** : `Dockerfile` + `scripts/deploy_space.py` (Space `rferrat/agora-mcp`). Les Spaces Docker
demandent un abonnement Hugging Face PRO (erreur 402 sans), d'où le choix de rester en local. Ne pas relancer le
déploiement sans accord explicite : il publie un service public.

## Conventions

- **Commits en français**, format `type(scope): description` en minuscules sans point final, corps qui explique le
  pourquoi (voir `git log`). Types : `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `sécurité`.
  Scopes courants : `mcp`, `llm`, `api`, `web`, `index`, `prompts`, `deploy`, `assemblee`, `ingestion`.
- Travail par branche + PR vers `main` (merge commit), CI verte avant merge.
- Docstrings et commentaires en français ; lignes ≤ 120 caractères (ruff).
