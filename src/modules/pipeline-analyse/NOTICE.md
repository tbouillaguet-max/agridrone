# Notice — Pipeline d'analyse des images du drone (v1.1.0)

Module : `src\modules\pipeline-analyse\`
Position dans le workflow : module **5**. Il vient **après** l'atterrissage et le transfert Wi-Fi (module 3, à faire), **après** le planificateur (module 1) qui archive la mission, et il **utilise** les modèles entraînés (module 4, export ONNX).

```
Planificateur ──► mission_<id>.json (+ culture) ───────────────────────────────┐
Drone AU2 ──► images\ + photos.csv + boite_noire.csv ──Wi-Fi──► vols\entrant\ ─┼─► [PIPELINE] ──► vols\<date>_<id>\rapport.html
Entraînement ──► *.onnx + modeles.json ────────────────────────────────────────┘
```

## 1. But

À partir des photos d'un vol, dire **s'il y a des plantes malades** (maladie ou ravageur) et **où**. Le pipeline produit un **rapport HTML** avec la carte 2D des zones malades et les statistiques de confiance, et met de côté les images incertaines pour les relabelliser.

## 2. Entrées

| # | Élément | Emplacement | Format | Produit par | Si absent ou non conforme |
|---|---|---|---|---|---|
| E1 | Photos du vol (≈ 100) | `<vol>\images\` | JPEG, nommées `IMG_0001.JPG`… | caméra (déclenchée par AU2), transfert Wi-Fi | **arrêt** |
| E2 | Journal du vol | `<vol>\photos.csv` | CSV `;`, UTF-8 sans BOM, point décimal, en-tête exacte | AU2 | **arrêt** |
| E3 | Mission avec culture et caméra | `data\missions\mission_<id>.json` (ou `_2`, `_3`…) | JSON v1 du planificateur + `"culture"` ; `camera` {`capteurLargeurMm`, `capteurHauteurMm`, `focaleMm`, `provisoire`} pour la localisation v2 | planificateur (`serveur_local.py`) | **arrêt** ; sans `camera` : v1 au lieu de v2 (avertissement) |
| E4 | Registre des modèles | `pipeline\modeles.json` | JSON v1, une entrée par culture | Tom (après entraînement) | **arrêt** |
| E5 | Boîte noire | `<vol>\boite_noire.csv` | CSV `;`, 11 colonnes | AU2 | facultative en v1 : avertissement si absente, **arrêt** si présente mais non conforme |

`<vol>` est le dossier déposé après le vol, par exemple `data\vols\entrant\mission_00012_01\`.

### E2 — `photos.csv` (contrat AU2, SPECIFICATION.md § 12.2)
```
fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission
IMG_0001.JPG;2026-11-02T14:05:12Z;48.3010580;1.6030366;10.00;87.5;0;12
```
Les contrôles sont les mêmes que ceux de `protocole\outils\verifier_fichiers_vol.py`, et les règles sont centralisées dans `analyse\contrat.py`.

### E3 — Choix de la mission
Le pipeline commence par lister `mission_<id>.json` et `mission_<id>_N.json`, puis applique ces filtres dans l'ordre :
1. les missions valides ;
2. celles qui ont assez de waypoints pour le plus grand `index_waypoint` du vol ;
3. si la boîte noire contient `MISSION_CHARGEE … mission <id>, <n> waypoints`, celles qui ont exactement n waypoints ;
4. la plus récente (`modifieLe`) sans dépasser le début du vol, à 10 min près.

S'il reste une ambiguïté, le pipeline s'arrête et demande `--mission <fichier>`.

### E3 — Caméra (localisation v2)
La v2 lit `camera.capteurLargeurMm`, `capteurHauteurMm` et `focaleMm` dans la mission. Tant que la mission n'écrit pas `"provisoire": false` dans `camera`, le pipeline considère ces paramètres comme **provisoires** : il calcule quand même la v2, mais l'avertit dans le journal et dans le rapport. **Écart à corriger côté planificateur :** `cameraProvisoire` existe dans `config.js` mais n'est pas recopié dans `mission.json` ; il faut l'écrire dans `camera.provisoire`. Le format des images (largeur / hauteur) doit être celui du capteur, à 3 % près, sinon un avertissement apparaît.

### E4 — Registre `modeles.json`
Les cultures du registre doivent être les mêmes que celles du planificateur (`ble`, `mais`, `pommier`). Les chemins sont relatifs au fichier du registre.

| `type` | Usage | Champs |
|---|---|---|
| `a_definir` | modèle pas encore choisi (état actuel) | arrêt avec message |
| `classification` | image entière ou **tuiles** | `onnx`, `classes`, `classe_malade`, `seuil`, `entree` {`largeur`, `hauteur`, `normalisation`: imagenet\|aucune, `disposition`: NCHW\|NHWC, `sortie`: logits\|probas, `redimensionnement`: etirer\|letterbox, `couleur_bandes` (114), `jpeg_qualite` (facultatif)}, `tuiles` {`taille_px`, `recouvrement_pct`} |
| `detection` | export ONNX Ultralytics YOLOv8/v11 | `onnx`, `classes`, `classes_malades`, `seuil`, `entree` {`taille`}, `seuil_iou` |
| `deux_etages` | pommier : feuilles, puis classification | `extracteur` {détection}, `classifieur` {classification}, `seuil` |
| `factice` | démonstration uniquement (`modeles_demo.json`) | `seuil`, `tuiles` |

Exemple de classification par tuiles :
```json
"ble": { "type": "classification", "onnx": "..\\runs\\ble\\<run>\\model\\best.onnx",
         "description": "EfficientNet-B0 tuiles 512", "classes": ["sain", "malade"], "classe_malade": "malade",
         "seuil": 0.5, "entree": { "largeur": 224, "hauteur": 224, "normalisation": "imagenet", "sortie": "logits" },
         "tuiles": { "taille_px": 512, "recouvrement_pct": 10 } }
```
Exemple pour le pommier : le classifieur de feuilles est préparé comme dans le notebook 01 (JPEG qualité 75, puis carré avec bandes grises 114) :
```json
"pommier": { "type": "deux_etages", "seuil": 0.5, "description": "feuilles YOLO + classifieur SAIN/MALADE",
  "extracteur": { "onnx": "...\\feuilles.onnx", "classes": ["feuille"], "entree": { "taille": 640 }, "seuil_extraction": 0.25 },
  "classifieur": { "onnx": "...\\pommier_cls.onnx", "classes": ["SAIN", "MALADE"], "classe_malade": "MALADE",
    "entree": { "largeur": 224, "hauteur": 224, "normalisation": "imagenet", "sortie": "logits",
                "redimensionnement": "letterbox", "couleur_bandes": 114, "jpeg_qualite": 75 } } }
```
`redimensionnement` vaut `etirer` par défaut : il faut le passer à `letterbox` pour tout modèle entraîné sur des images carrées à bandes grises, sinon les feuilles découpées sont déformées.

**Contrat d'un modèle :** ONNX sur CPU. Il reçoit une image, une tuile ou une feuille. Il renvoie la probabilité « malade » ; un détecteur renvoie en plus des boîtes. Une image est **malade** si au moins un élément atteint le seuil, et son **score** est celui de l'élément le plus sûr.

## 3. Sorties

Toutes dans `data\vols\<AAAA-MM-JJ>_<id>\`. Si ce dossier existe déjà, le pipeline crée `_2`, `_3`… et n'écrase jamais rien. `vols\entrant\` n'est pas modifié.

| # | Sortie | Contenu |
|---|---|---|
| S1 | `brut\` | copie des entrées (images, CSV, mission retenue), **en lecture seule** |
| S2 | `resultats\images.csv` | `fichier;statut;score;nb_detections;nb_elements;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;dans_limites;remarque` |
| S3 | `resultats\detections.csv` | `fichier;classe;score;x1;y1;x2;y2;lat;lon;localisation` : éléments au-dessus du seuil ; boîte vide si l'image entière est classée. En v2, `lat;lon` est la position au sol du centre de la boîte ; en v1, la position du drone |
| S4 | `resultats\zones_malades.geojson` | cases malades de la grille, avec `cote_cellule_m` et `localisation` dans les propriétés de la collection. Propriétés d'une case : `nb_images` (v2 : photos dont l'emprise couvre la case), `nb_malades` (photos où la case est vue malade), `part_malades`, `nb_detections` (v2), `confiance_moyenne`, `confiance_max`, `fichiers_malades` |
| S5 | **`rapport.html`** | page autonome : verdict, chiffres clés, alertes, carte IGN, top des malades, images à vérifier |
| S6 | `a_relabelliser\` | les N images les plus proches du seuil, avec `a_relabelliser.csv` et une colonne `label_corrige` à remplir |
| S7 | `journal_pipeline.txt` | déroulé horodaté, avertissements |
| — | `vols\_echecs\<horodatage>_<vol>.txt` | journal d'un arrêt : erreurs avec fichier, ligne et module fautif |

Le rapport contient :
- le nombre d'images analysées et le nombre d'images malades ;
- la confiance moyenne des malades ;
- le **top 10** des malades les plus sûres (toutes, s'il y en a moins de 10) ;
- les **10 images les moins sûres** ;
- les alertes CRITIQUE et URGENCE de la boîte noire ;
- un bandeau rouge si le modèle est factice ;
- une carte avec les fonds orthophotos IGN, plan IGN et OSM, comme dans le planificateur.

Leaflet est intégré dans la page : seuls les fonds de carte demandent une connexion.

## 4. Fonctionnement

```
python pipeline.py "data\vols\entrant\mission_00012_01"
```
Tu peux aussi glisser le dossier du vol sur `analyser.bat`. Les options sont décrites par `python pipeline.py -h` : `--localisation auto|v1|v2` (défaut `auto` : v2 si la mission donne la caméra), `--verifier`, `--mission`, `--modeles`, `--nb-top`, `--nb-incertaines`, `--missions`, `--sortie`.

| Étape | Rôle | Arrêt si… |
|---|---|---|
| 0. Réception | transfert Wi-Fi vers `vols\entrant\` (**hors v1**) | — |
| 1. Validation | E1, E2, E5 (fichiers, colonnes, formats, une image par ligne et inversement, images lisibles, un seul `id_mission`), puis E3 (choix et contrôle de la mission, `index_waypoint` dans la mission) ; photos hors des limites : avertissement | **oui**, avec toutes les erreurs d'un coup |
| 3. Choix du modèle | `culture` → entrée du registre, ONNX présents et chargeables (fait avant la sauvegarde : une configuration incomplète ne crée aucun dossier) | **oui** |
| 2. Sauvegarde | copie dans `brut\`, en lecture seule | erreur disque |
| 4. Analyse | inférence image par image sur CPU ; une image en erreur est signalée et exclue | si aucune image n'a pu être analysée |
| 5. Localisation | **v2 (par défaut)** : chaque détection est projetée au sol, puis chaque case de 2 m recouverte par une boîte projetée devient malade (une image entière classée malade recouvre toute son emprise). **v1** (sans caméra, ou `--localisation v1`) : position du drone = centre de la photo, grille de côté = petit côté de l'emprise | `--localisation v2` sans caméra dans la mission |
| 6. Rapport | `rapport.html`, CSV, GeoJSON, `a_relabelliser\` | — |

**Géométrie de la v2.** Hypothèses validées avec Tom :
- caméra visée verticale (nadir), modèle sténopé sans distorsion, sol plat ;
- le haut de l'image est l'avant du drone, donc la direction `cap_deg` (0 = nord, sens horaire).

Un pixel (u, v) d'une image W × H prise à l'altitude h donne au sol :
- `dx = (u/W − ½) · h · capteurLargeur / focale` vers la droite du drone ;
- `dy = (½ − v/H) · h · capteurHauteur / focale` vers l'avant ;
- puis `est = dx·cos(cap) + dy·sin(cap)` et `nord = −dx·sin(cap) + dy·cos(cap)`, ajoutés à la position GPS.

La précision dépend du GPS, du cap et de la distorsion de l'objectif. Sur la démo (bruit GPS ± 0,4 m, cap ± 1,5°), toutes les détections tombent dans leur foyer à moins de 1 m près ; en v1, l'écart atteint 7,8 m.

**Codes de sortie :**
- `0` : terminé ;
- `1` : entrées non conformes ou configuration incomplète ;
- `2` : erreur inattendue.

**Règle de cohérence (consigne du projet) :** chaque erreur nomme le fichier, la ligne et le module fautif : `drone (AU2)`, `caméra ou transfert Wi-Fi`, `planificateur` ou `registre des modèles / entraînement`.

## 5. Démonstration et tests

- `demo.bat` (ou `python outils\creer_vol_demo.py --alerte-critique`) fabrique dans `pipeline\demo\` un vol conforme : 104 photos synthétiques, deux foyers, une alerte batterie critique. Il l'analyse ensuite avec `modeles_demo.json`, qui contient un modèle **factice** sans valeur agronomique. Ce vol utilise la mission 9001 et ne touche jamais `data\missions`.
- `python -m pytest tests` lance 44 tests :
  - le bout en bout ;
  - un test par contrôle d'entrée ;
  - le choix de la mission avec suffixe ;
  - un vrai modèle ONNX construit à la volée ;
  - le décodage YOLO et le NMS ;
  - les deux étages ;
  - le letterbox et la recompression JPEG du classifieur ;
  - la géométrie de la v2 (aller-retour pixel ↔ sol, sens du cap), sa précision sur la démo et le choix du mode.
- Dépendances : `pip install -r requirements.txt` (numpy, pillow, onnxruntime ; pytest et onnx pour les tests).

## 6. Limites connues et suite
- **Modèles :** les trois cultures sont en `a_definir`. Il faut renseigner `modeles.json` quand les modèles seront retenus. Le format de sortie RT-DETR n'est pas encore pris en charge : seul YOLOv8/v11 l'est pour la détection.
- **Localisation v2 :** elle repose sur des paramètres caméra provisoires tant que la caméra n'est pas choisie. Elle ignore la distorsion de l'objectif, ce qui compte pour un grand-angle : il faudra ajouter une calibration (coefficients de distorsion) une fois la caméra choisie. Elle suppose une visée verticale : une nacelle inclinée ou un drone penché en vol décalent les positions, car le roulis et le tangage ne sont pas dans `photos.csv`.
- **Plus tard :** réception Wi-Fi et lancement automatique (l'appel `analyse.executer(Options(...))` renvoie un `Bilan` réutilisable), puis envoi du rapport.

## 7. Dépendances avec les autres modules
| Module | Doit fournir | État |
|---|---|---|
| Planificateur | `mission_<id>.json` v1 avec `culture` ; `camera` avec `provisoire` | culture faite ; **`camera.provisoire` à ajouter** ; caméra provisoire |
| Drone (AU2) | `photos.csv` et `boite_noire.csv` (§ 12), photos nommées comme dans le journal ; `MISSION_CHARGEE` avec « mission N, W waypoints » | contrat fixé |
| Transfert Wi-Fi | dépôt dans `vols\entrant\<vol>\` | à faire |
| Entraînement | ONNX + entrée dans `modeles.json` | en cours |
