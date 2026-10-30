# Module : `ml-dashboard`

> Dossier : `src/modules/ml-dashboard/`. Format des runs : [`STANDARD.md`](STANDARD.md). Notices : `docs/notices/` (livrables 1 à 3).

## 1. Rôle
Définit le format unique d'un run d'entraînement (`schema_version: 1`) et le valide, quel que soit le framework (PyTorch, timm, Ultralytics, scikit-learn). Le dashboard Streamlit recalcule les métriques depuis les prédictions brutes.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : package `ml_dashboard` ; CLI `python -m ml_dashboard validate <chemin>`.
- **Entrées** : dossier de run `data/runs/<projet>/<run_id>/` (`meta.json`, `config.yaml`, `predictions/*.csv`…).
- **Sorties** : rapport de validation (code de sortie 0 = valide, 1 = run invalide, 2 = aucun run).
- **État du code** : livrable 1 seulement (standard, schémas, validation, version 0.1.0). RunLogger (livrable 2), adaptateurs PyTorch / Ultralytics / sklearn (livrable 3), `import` (livrable 4), `export` vers `pipeline-analyse/modeles.json` : décrits dans `docs/notices/` mais absents de ce dépôt.

## 3. Dépendances Déclarées
- **Consomme** : aucun
- **Fournit à** : `pipeline-analyse` (export prévu), `detection-pommier`, `detection-mais`
- **Données (`data/`)** : lit `data/runs/`

## 4. Commandes Propres
Depuis `src/modules/ml-dashboard/`.
- **Techno** : Python ≥ 3.10
- **Installer** : `pip install -e .[dev]`
- **Lint / Build** : aucun configuré
- **Tests** : `python -m pytest` (inclut les doctests)

## 5. Règle d'Isolation (Interdits)
- Ne jamais figer d'images de métriques : tout se recalcule depuis `predictions/*.csv`.
- Ne jamais changer `schema_version` sans migration et mise à jour de `STANDARD.md`.
- L'export vers `modeles.json` écrit le format du pipeline (voir `docs/contrats.md`) et rien d'autre.
