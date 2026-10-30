# Module : `detection-mais`

> Dossier : `src/modules/detection-mais/`. Inventaire et choix d'approche : [`LIVRABLE_1_inventaire.md`](LIVRABLE_1_inventaire.md). Entraînement : [`LIVRABLE_3_entrainement.md`](LIVRABLE_3_entrainement.md). Sources : `SOURCES.csv`.

## 1. Rôle
Inventaire vérifié des jeux de données maïs, préparation des données et entraînement comparatif (YOLO, tuiles EfficientNet / MobileNet, RT-DETR) pour détecter maladies et ravageurs du maïs.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `notebooks/01_preparation_donnees.py` puis `notebooks/02_entrainement_comparaison.py` (`.ipynb` générés).
- **Entrées** : jeux publics listés dans `SOURCES.csv` (KaraAgro, Makerere, MLD, PlantDoc, Cornell NLB…) déposés dans `data/datasets/mais/` (`raw/`, `curated/`, `labels/`) ; vide pour l'instant.
- **Sorties** : jeux préparés dans `data/datasets/mais/`, runs au standard `ml-dashboard` dans `data/runs/`, puis modèle ONNX pour `pipeline-analyse`. Aucun modèle n'est encore exporté.

## 3. Dépendances Déclarées
- **Consomme** : `ml-dashboard` (standard de run, RunLogger)
- **Fournit à** : `pipeline-analyse` (entrée `mais` de `modeles.json`, aujourd'hui `a_definir`)
- **Données (`data/`)** : `data/datasets/mais/`, `data/runs/`

## 4. Commandes Propres
Depuis `src/modules/detection-mais/`.
- **Techno** : notebook Python (script `# %%` converti en `.ipynb`)
- **Installer** : dépendances listées dans les notebooks
- **Lint / Build** : `python scripts/build_notebook.py`
- **Tests** : `python scripts/test_prep_synthetic.py` ; `python scripts/test_train_synthetic.py`

## 5. Règle d'Isolation (Interdits)
- Ne jamais modifier `raw/` ; respecter les licences de `SOURCES.csv`.
- Les classes du `data.yaml` doivent être celles du run (sinon arrêt avant la 1re époque).
- Un export vers le pipeline respecte le format de `modeles.json` (RT-DETR : seulement une fois le type accepté par le pipeline).
