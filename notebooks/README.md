# notebooks/

Exploration et visualisation uniquement : toute logique réutilisable (chargement,
découpage, métriques) vit dans `src/agridrone/` et y est testée.

- Lancer : `uv sync --group notebooks && uv run jupyter lab`.
- Nommage : `NN_sujet.ipynb` (ex. `01_exploration_pucerons.ipynb`).
- Vider les sorties avant de committer (images lourdes, chemins locaux).
