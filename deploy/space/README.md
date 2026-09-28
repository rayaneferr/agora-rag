---
title: Agora MCP
emoji: 🏛️
colorFrom: yellow
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: MCP publics RAG, films et débats de l'Assemblée
---

# Agora — serveurs MCP publics

Recherche sémantique (bge-m3 + LanceDB) exposée en **MCP**, publique, en lecture seule, sans clé :

| Contexte | Endpoint | Archives |
|---|---|---|
| La Salle obscure | `https://rferrat-agora-mcp.hf.space/cinema/mcp` | ~35 000 synopsis de films (Wikipédia) |
| L'Hémicycle | `https://rferrat-agora-mcp.hf.space/assemblee/mcp` | séances de l'Assemblée nationale (17e législature) |

```bash
claude mcp add --transport http agora-assemblee https://rferrat-agora-mcp.hf.space/assemblee/mcp
claude mcp add --transport http agora-cinema https://rferrat-agora-mcp.hf.space/cinema/mcp
```

État du service : [`/health`](https://rferrat-agora-mcp.hf.space/health).

Code, architecture et application locale : [github.com/rayaneferr/agora-rag](https://github.com/rayaneferr/agora-rag).
Ce Space est déployé depuis ce dépôt par `scripts/deploy_space.py` : ne pas le modifier ici.
