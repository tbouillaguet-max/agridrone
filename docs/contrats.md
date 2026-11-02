# Contrats entre modules

Formats de fichiers et chemins échangés. Les liens du graphe sont dans [`GRAPH.md`](../GRAPH.md). Source d'origine : `docs/notices/notice_workflow.md` (conservée comme historique). Racine des données : `DRONE_DATA_DIR`, sinon `data/`.

## `planificateur` → `pipeline-analyse` : `data/missions/mission_<id>.json`
- JSON version 1. Champ `culture` obligatoire, dans {`ble`, `mais`, `pommier`}.
- Liste des cultures identique dans `planificateur/js/config.js`, `planificateur/serveur_local.py` (`CULTURES`), `pipeline-analyse/modeles.json`, `pipeline-analyse/analyse/contrat.py`.
- `camera` {`capteurLargeurMm`, `capteurHauteurMm`, `focaleMm`, `provisoire`} sert à la localisation v2 du pipeline.
- Si l'id existe déjà avec un autre contenu, le planificateur écrit `mission_<id>_2.json`, `_3`… (jamais d'écrasement). Le pipeline choisit la mission par filtre sur les waypoints, la boîte noire, puis `modifieLe` ; sinon option `--mission`.
- **Écart** : le planificateur n'écrit pas `camera.provisoire` (reste dans `config.js`). Le pipeline considère la caméra comme provisoire et avertit à chaque vol jusqu'à `"provisoire": false`.
- `data/missions/journal_planificateur.txt` : `horodatage UTC \t NIVEAU \t mission N \t texte`.

## `planificateur` ↔ `au1-au2` : protocole v1
- Câble USB, 115 200 bauds, trames `AA 55`. Mission envoyée avec relecture octet par octet et CRC.
- Refus si le drone est armé ou en vol (`ETAT_INCOMPATIBLE`). La culture n'est jamais transmise au drone.
- Référence : `src/modules/protocole/SPECIFICATION.md`.

## `au1-au2` → `pipeline-analyse` : dossier de vol (via `transfert-wifi`) dans `data/vols/entrant/<vol>/`
- `images/IMG_0001.JPG`… (JPEG).
- `photos.csv` : `fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission` (CSV `;`, UTF-8 sans BOM, point décimal, en-tête exacte). `cap_deg` et `altitude_rel_m` servent à la localisation v2 : haut de l'image = avant du drone = cap, caméra visée verticale.
- `boite_noire.csv` : `horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail`. Facultatif en v1 (avertissement si absent, arrêt si non conforme). `MISSION_CHARGEE` (« mission N, W waypoints ») sert au choix de la mission.
- Ces colonnes ne changent jamais sans prévenir. Contrôle : `python src/modules/protocole/outils/verifier_fichiers_vol.py <dossier>`.
- Le vol de démonstration du pipeline (`outils/creer_vol_demo.py`) doit passer ce contrôle.

## `pipeline-analyse` → Tom : `data/vols/<AAAA-MM-JJ>_<id>/`
`rapport.html`, `resultats/` (`images.csv`, `detections.csv`, `zones_malades.geojson`), `a_relabelliser/`, `brut/`. Un dossier existant n'est jamais écrasé (`_2`, `_3`…).

## `ml-dashboard` → `detection-*` : standard de run v1
- Dossier `data/runs/<projet>/<run_id>/` (`meta.json`, `config.yaml`, `predictions/*.csv`…), vérifié par `python -m ml_dashboard validate <dossier>`. Détail : `src/modules/ml-dashboard/STANDARD.md`.
- Classes du `data.yaml` = classes du run (sinon arrêt avant la 1re époque).
- `detection-pommier` : classes de `classes.json` (`SAIN`, `MALADE`, positive `MALADE`, single) passées à `RunLogger.start` ; `manifest.id` comme ids, `sous_source` comme groups.

## `detection-*` / `ml-dashboard` → `pipeline-analyse` : modèles ONNX + `modeles.json`
- ONNX exécutable sur CPU, déclaré dans `src/modules/pipeline-analyse/modeles.json` : `{"version": 1, "cultures": {culture: {type, onnx, classes, classe_malade | classes_malades, seuil, entree {…}, tuiles {…}}}}`. Types : `classification`, `detection` (YOLOv8/v11), `deux_etages`. Chemins relatifs à `modeles.json`.
- Un modèle entraîné sur images carrées à bandes grises (pommier) exige `entree.redimensionnement: "letterbox"`, `couleur_bandes: 114`, `jpeg_qualite: 75`.
- Un simple `{culture: {type, onnx, classes, seuil}}` est refusé (« registre des modèles »).
- **État** : `a_definir` pour les trois cultures ; l'export `python -m ml_dashboard export <run> --culture <ble|mais|pommier>` n'existe pas encore.

## Points ouverts (à reprendre module par module)
1. Modèle de caméra programmable, puis `camera.provisoire: false` ; calibration de la distorsion pour la v2 du pipeline.
2. Module `transfert-wifi`, puis lancement automatique du pipeline en fin de transfert.
3. Export `ml-dashboard` → `modeles.json` ; prise en charge de RT-DETR dans le pipeline.
4. Pommier `deux_etages` : données et modèle de l'extracteur de feuilles sur image de drone.
5. Roulis et tangage au moment de la photo absents de `photos.csv`.
6. Envoi du rapport.
7. Contrat de sortie de `ml-agridrone` vers `modeles.json`.
