# Module : `pipeline-analyse`

> Dossier : `src/modules/pipeline-analyse/`. Spécification complète (entrées E1–E5, sorties, tests) : [`NOTICE.md`](NOTICE.md). Version 1.1.0 (localisation v2).

## 1. Rôle
À partir des photos d'un vol, dit s'il y a des plantes malades (maladie ou ravageur) et où : rapport HTML avec carte des zones malades et statistiques de confiance, images incertaines mises de côté pour relabellisation.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `pipeline.py <dossier_vol>` (options `--missions`, `--modeles`, `--sortie`, `--mission`) ; `analyser.bat` (glisser le dossier du vol) ; `demo.bat` (vol de démonstration).
- **Entrées** :
  - E1 `<vol>/images/IMG_xxxx.JPG`, E2 `<vol>/photos.csv`, E5 `<vol>/boite_noire.csv` (contrat `protocole`) ;
  - E3 `data/missions/mission_<id>.json` (contrat `planificateur`, avec `culture` et `camera`) ;
  - E4 `modeles.json` du module (registre des modèles ONNX par culture).
- **Sorties** : `data/vols/<AAAA-MM-JJ>_<id>/` avec `rapport.html`, `resultats/` (`images.csv`, `detections.csv`, `zones_malades.geojson`), `a_relabelliser/`, `brut/`. Jamais d'écrasement.
- Formats exacts : `docs/contrats.md`.

## 3. Dépendances Déclarées
- **Consomme** : `planificateur` (missions), `protocole` (format des fichiers de vol), `ml-dashboard` et `detection-*` (modèles ONNX + `modeles.json`)
- **Fournit à** : aucun (Tom lit le rapport)
- **Données (`data/`)** : lit `data/missions/`, `data/vols/entrant/` ; écrit `data/vols/`. Racine : `DRONE_DATA_DIR`, sinon `<racine>/data`.

## 4. Commandes Propres
Depuis `src/modules/pipeline-analyse/`.
- **Techno** : Python
- **Installer** : `outils\env_python.bat` (crée l'environnement `%USERPROFILE%\drone-workflow` et installe `requirements.txt`) ou `pip install -r requirements.txt`
- **Lancer** : `python pipeline.py <dossier_vol>` ; démonstration : `demo.bat`
- **Tests** : `python -m pytest tests` (ou `lancer_tests.bat`, résultat dans `tests_windows.log`)

## 5. Règle d'Isolation (Interdits)
- Ne jamais écraser un dossier de résultats ni modifier les fichiers du vol (copie dans `brut/`).
- Le format de `modeles.json` est fixé ici : tout export de modèle doit s'y conformer (voir `docs/contrats.md`).
- La liste des cultures reste identique à celle du planificateur (`analyse/contrat.py`).
- Aucun chemin absolu ; ne jamais importer le code interne d'un autre module.
