import os

# LiteLLM télécharge sa grille de prix à l'import : on garde la copie livrée avec le paquet (tout est gratuit
# en local de toute façon). Posé ici pour précéder tout import de litellm.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
