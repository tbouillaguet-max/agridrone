# Module : `ml-agridrone`

> Dossier : `src/modules/ml-agridrone/`. Installation, téléchargement des données, détail des projets : [`GUIDE.md`](GUIDE.md). Sous-projets : `ble/`, `olivier/`.

## 1. Rôle
Pile ML autonome du drone pour deux cultures : classifieur des maladies du blé, segmentation multispectrale N bandes, inventaire de données et TP pour l'olivier, avec entraînement, évaluation, suivi MLflow et export ONNX. Repris de l'ancien dépôt `drone`, intégré tel quel.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : package `agridrone` (`src/agridrone/`), CLI `agridrone` (`info`, `smoke`, `data`, `train`, `evaluate`…).
- **Entrées** : registres de sources `ble/configs/data/sources.yaml` et `olivier/configs/data/sources.yaml` ; configs d'expériences YAML.
- **Sorties** : données dans `src/modules/ml-agridrone/data/<projet>/`, runs dans `runs/<projet>/` (local au module, ignorés par Git), modèles ONNX (`export/onnx.py`).

## 3. Dépendances Déclarées
- **Consomme** : aucun
- **Fournit à** : `pipeline-analyse` (modèles ONNX ; contrat avec `modeles.json` à définir)
- **Données (`data/`)** : aucune dans le `data/` racine ; garde ses propres `data/` et `runs/` (écart connu, voir `GRAPH.md`)

## 4. Commandes Propres
Depuis `src/modules/ml-agridrone/`.
- **Techno** : Python 3.12, gestionnaire `uv`
- **Installer** : `uv sync` (`uv sync --group notebooks` pour JupyterLab)
- **Lint / Build** : `uv run ruff check .` ; `uv run mypy`
- **Tests** : `uv run pytest`

## 5. Règle d'Isolation (Interdits)
- Les projets `ble/` et `olivier/` ne partagent aucune source de données ; seul le code de `src/agridrone/` est commun.
- Ne jamais versionner données, runs, poids (`*.pt`, `*.onnx`), `mlflow.db` ni clés (`.env`, `kaggle.json`).
- Racine du module : `AGRIDRONE_ROOT` ou détection par `pyproject.toml` + `configs/` ; ne pas déplacer ces deux éléments.
