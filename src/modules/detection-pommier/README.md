# Module : `detection-pommier`

> Dossier : `src/modules/detection-pommier/`. Détail des sources et du notebook : [`GUIDE.md`](GUIDE.md). Notice : `docs/notices/notice_apple_preparation_donnees.md`. Sources : `SOURCES.csv`.

## 1. Rôle
Prépare les données et entraîne la détection sain / malade sur feuilles de pommier (v1 : classification binaire, classe positive `MALADE`), à partir d'AppleLeaf9, FGVC8 « healthy », PlantDoc et GYMNSA (tuiles de drone).

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `notebooks/01_preparation_donnees.py` (`.ipynb` généré, exécuté sur Kaggle, CPU).
- **Entrées** : `data/datasets/pommier/raw/` (appleleaf9, gymnsa, plantdoc_apple) et `archives/` ; FGVC8 comme Input Kaggle.
- **Sorties** : `apple_prep/` avec `cls/{train,val,test,test_externe}/{SAIN,MALADE}`, `drone/`, `manifest.csv`, `classes.json`, rapports. L'entraînement (notebook 02) n'est pas écrit.

## 3. Dépendances Déclarées
- **Consomme** : `ml-dashboard` (classes de `classes.json` passées à `RunLogger.start`)
- **Fournit à** : `pipeline-analyse` (modèle `deux_etages` : classifieur de feuilles ; l'extracteur de feuilles manque)
- **Données (`data/`)** : `data/datasets/pommier/`, `data/runs/`

## 4. Commandes Propres
Depuis `src/modules/detection-pommier/`.
- **Techno** : notebook Python (script `# %%` converti en `.ipynb`)
- **Installer** : dépendances listées dans le notebook (environnement Kaggle)
- **Lint / Build** : `python scripts/build_notebook.py` (`.py` → `.ipynb`)
- **Tests** : `python scripts/test_echantillon.py` (faux FGVC8 piégé : doublons, conflits, copie PlantDoc)

## 5. Règle d'Isolation (Interdits)
- Ne jamais modifier `raw/` (immuable, sommes de contrôle dans `SOURCES.csv`).
- Découpage train/val/test sans fuite : par sous-source, jamais aléatoire par image.
- Ne jamais ajouter de chemin absolu : renseigner `LOCAL_DIRS` depuis `DRONE_DATA_DIR`.
