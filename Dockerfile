# Serveurs MCP publics d'Agora (agora-mcp-public), pour un Space Hugging Face ou tout hôte Docker.
#
# L'index et bge-m3 sont téléchargés à la construction, à la révision épinglée et vérifiés empreinte par
# empreinte (agora-index import) : l'image démarre sans réseau et sert exactement la version validée.
#
#   docker build -t agora-mcp .
#   docker run -p 7860:7860 agora-mcp          # http://127.0.0.1:7860/health

# Images de base épinglées par empreinte, comme les actions de la CI.
FROM ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c AS uv
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

COPY --from=uv /uv /usr/local/bin/uv

# Les Spaces lancent le conteneur avec l'UID 1000 : tout ce qu'on écrit doit lui appartenir.
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/app/.venv/bin:$PATH \
    AGORA_HOME=/home/user/data \
    HF_HOME=/home/user/.cache/huggingface \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /home/user/app

# Dépendances d'abord (torch CPU sous Linux, cf. pyproject) : cette couche survit aux changements de code.
COPY --chown=user pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY --chown=user src ./src
RUN uv sync --locked --no-dev

# Index (~890 Mo) + bge-m3 (~2,3 Go), vérifiés contre les empreintes publiées par le Hub.
RUN agora-index import

# À l'exécution, plus aucun accès au Hub : tout est dans l'image.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PORT=7860 \
    MCP_ALLOWED_HOSTS=rferrat-agora-mcp.hf.space
EXPOSE 7860
CMD ["agora-mcp-public", "--host", "0.0.0.0", "--allow-remote"]
