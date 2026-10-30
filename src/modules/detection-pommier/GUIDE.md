# apple-detection — détection sain / malade sur feuilles de pommier

Travail académique. Objectif v1 : classification binaire SAIN / MALADE (positive_class = MALADE).
Position dans le workflow : étape 4 (entraînement) — voir la notice « notice_apple_preparation_donnees » du projet.

## Données brutes (raw/) — voir SOURCES.csv
- raw/appleleaf9 : 14 582 images, 9 dossiers. `Health` = SAIN, les 8 autres = MALADE.
- raw/gymnsa : tuiles drone (5-12 m) de verger de poiriers, rouille ; boîtes YOLO ; label vide = sans symptôme.
- raw/plantdoc_apple : petit jeu web, test externe uniquement.
- archives/ : zip original GYMNSA (SHA-256 vérifié).
- FGVC8 : pas de copie locale ; ajouté comme Input dans le notebook Kaggle (feuilles saines seulement).

## notebooks/
- 01_preparation_donnees (.py / .ipynb) : sources → harmonisation (958 px + JPEG 75) → dédoublonnage →
  découpage sans fuite → `apple_prep/` (cls/, drone/, manifest.csv, classes.json, rapports).
  Sur Kaggle : Input = compétition plant-pathology-2021-fgvc8, Internet On, CPU ; d'abord RUN_MODE="inventaire".

## scripts/
- build_notebook.py : .py (« # %% ») → .ipynb.
- test_echantillon.py : test local du notebook 01 avec un faux FGVC8 piégé (doublons, conflit, copie PlantDoc).

## logs/
Scripts de téléchargement (dl_github.py reprenable).
