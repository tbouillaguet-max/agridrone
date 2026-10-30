# ble/notebooks/

Notebooks du projet blé. Exploration et visualisation uniquement : toute logique
réutilisable (chargement, découpage, métriques) vit dans `src/agridrone/` et y est testée.

- Lancer, depuis la racine du dépôt : `uv sync --group notebooks && uv run jupyter lab ble/notebooks/`.
- Données lues dans `data/ble/`, figures écrites dans `ble/reports/figures/`.
- Nommage : `NN_sujet.ipynb` (ex. `01_exploration_donnees.ipynb`).
- Vider les sorties avant de committer (images lourdes, chemins locaux).

Les notebooks du projet olivier (TP maladies et parasites) sont dans `olivier/tp/`.
