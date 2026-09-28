# CLAUDE.md — agora-rag

Serveurs MCP de RAG sémantique (bge-m3 + LanceDB) sur deux corpus — débats de l'Assemblée nationale, synopsis de
films — destinés à être branchés sur Claude, en local. Les serveurs cherchent et citent ; ils ne rédigent rien.
Le README raconte l'évolution du projet et justifie les choix : le lire avant de proposer un changement de cap.
L'ancienne application locale (React + Ollama) et le déploiement Hugging Face ont été retirés en v0.7 ; ils restent
au tag `v0.6.0`.

## Commandes

```bash
uv sync                                   # dépendances (torch CPU sous Linux, cf. [tool.uv.sources])
uv run agora-index import                 # index (~890 Mo) + bge-m3 (~2,3 Go) → data/ et cache HF, empreintes vérifiées
uv run pytest                             # rapide (~2 s) : ni bge-m3 ni index
uv run ruff check . && uv run ruff format --check .

uv run mcp-assemblee | mcp-cinema         # un serveur MCP en stdio (--transport http pour le servir en HTTP)
uv run agora-mcp-public                   # tous les contextes sur :8100 (/<contexte>/mcp, /health)
uv run python scripts/smoke_test.py       # vérifie agora-mcp-public avec l'index réel
```

La CI (`.github/workflows/ci.yml`) lance exactement ruff et pytest.

## Architecture (par contextes)

- `src/agora/core/` : `ContextSpec` (description, provenance `DataSource`, étendue) et découpage de texte.
  **N'importe que la bibliothèque standard et lui-même** — `tests/test_architecture.py` le vérifie (`STDLIB_OK`).
- `src/agora/contexts/<nom>/` : `__init__.py` (le `SPEC`), `server.py` (outils, prompts et resource MCP),
  `ingestion.py`. **Un contexte n'importe jamais un autre contexte** (testé aussi). Nouveau contexte = nouveau
  dossier + inscription dans `contexts/__init__.py` ; il est alors exposé en stdio et par `agora-mcp-public`.
- `src/agora/adapters/inbound/mcp_public.py` : tous les contextes en HTTP sur un port, avec garde-fous.
- `src/agora/adapters/outbound/` : `vectorstore.py` (LanceDB + bge-m3), `mcp_serve.py` (lancement stdio/HTTP,
  `archives()`, `guided_prompt()`), `index_hub.py` (index ↔ Hugging Face), `dataset_card.md` (carte de l'index).

## Invariants à ne pas casser

- **Révisions épinglées** : `INDEX_REVISION` (index_hub.py) et `EMBED_REVISION` (vectorstore.py). Tout fichier
  téléchargé est vérifié contre les empreintes du Hub. Ne jamais charger bge-m3 sans révision (poids = pickle).
- **Filtres SQL** : toute valeur venant du modèle passe par `vs.quote()` ou `int()` avant d'entrer dans un `where`.
- **Exposition réseau** : écoute non locale seulement avec `--allow-remote`. `mcp_public.py` : hôtes/origines
  autorisés, corps ≤ 64 Ko, débit par IP, pas de journal d'accès.
- **Prompts MCP** (`RULES` dans chaque `server.py`) : des règles de sourçage pour l'assistant de l'utilisateur
  (citer, dater, lier, rester neutre, ne pas conclure au-delà de la fin des archives).
- **L'étendue des archives** est toujours calculée depuis l'index (`ContextSpec.coverage_text`), jamais écrite en dur.
- **Licences des données** : chaque contexte déclare ses `sources` (producteur, licence), exposées par la resource
  `<contexte>://archives`. Films : CC BY-SA 4.0 (partage à l'identique pour l'index). Débats : Licence Ouverte
  (Etalab, octobre 2011) — citer « Assemblée nationale » et la date des données. Garder README, NOTICE.md et
  `dataset_card.md` alignés si une source change ; ne jamais retirer les liens (`wiki_url`, `url`) des résultats.

## Pièges connus

- Starlette ne lance pas le `lifespan` des apps montées : `mcp_public.py` démarre lui-même chaque
  `session_manager` ; sans ça, toutes les requêtes MCP échouent.
- bge-m3 se charge en tâche de fond (`warm_up`, ~20 s) : `/health` répond 503 `starting` tant qu'il n'est pas prêt.
- Les tests remplacent `vs.embed` par un embedder factice et `vs.DB_DIR` par un dossier temporaire (`conftest.py`) ;
  tester les outils **à travers le protocole MCP** (client en mémoire), pas en appel Python direct.
- Les synopsis sont en anglais : les requêtes `search_films` en anglais donnent de meilleurs résultats.
- La carte de l'index (`dataset_card.md`) n'est poussée sur Hugging Face que par `agora-index publish` : la
  modifier dans le dépôt ne met pas à jour le Hub.

## Conventions

- **Commits en français**, format `type(scope): description` en minuscules sans point final, corps qui explique le
  pourquoi (voir `git log`). Types : `feat`, `fix`, `refactor`, `docs`, `test`, `ci`, `chore`, `sécurité`.
  Scopes courants : `mcp`, `index`, `prompts`, `assemblee`, `cinema`, `ingestion`.
- Travail par branche + PR vers `main` (merge commit), CI verte avant merge.
- Docstrings et commentaires en français ; lignes ≤ 120 caractères (ruff).
