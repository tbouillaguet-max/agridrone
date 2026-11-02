# Notice — Pommier, notebook 01 : préparation des données (SAIN / MALADE)

Module : `src\modules\detection-pommier\notebooks\01_preparation_donnees.py` (+ `.ipynb`)
Test : `apple-detection\scripts\test_echantillon.py` ; conversion : `scripts\build_notebook.py`
Position dans le workflow : étape 4 (entraînement), **avant** le notebook 02 d'entraînement pommier (à écrire). Exécution sur Kaggle (CPU, Internet On), ou en local avec `LOCAL_DIRS`.

```
AppleLeaf9 (GitHub) ─┐
FGVC8 « healthy » ───┤ (Input Kaggle)      ┌─► cls/{train,val,test}/{SAIN,MALADE}     ─► notebook 02 → RunLogger (L2) → runs\pommier\
PlantDoc pommier ────┼─► [notebook 01] ────┼─► cls/test_externe/{SAIN,MALADE}
GYMNSA (Mendeley) ───┘                     └─► drone/cls + drone/det (YOLO)            ─► adaptation drone (plus tard)
```

## 1. But
Construire un jeu binaire SAIN / MALADE **sans raccourci de source**. Constat du 30/10/2026 :
- AppleLeaf9 : les 516 feuilles saines viennent toutes de FGVC2020 (2048×1365). Les malades viennent surtout de FGVC2021 réduites (958×640) et d'ATLDSD (512×512, aucune feuille saine). Tout est en JPEG qualité 75.
- GYMNSA : 158 des 162 tuiles sans symptôme sont en JPEG ~100, contre 75 pour toutes les tuiles malades.

Sans traitement, un modèle peut apprendre la source (taille, compression) au lieu de la maladie.

## 2. Entrées
| Source | Accès | Utilisation |
|---|---|---|
| AppleLeaf9 (CC BY 4.0) | téléchargé depuis GitHub, ou `LOCAL_DIRS`, ou Input Kaggle | `Health` → SAIN ; 8 autres dossiers → MALADE |
| FGVC8 (règlement Kaggle) | **Input Kaggle** : compétition `plant-pathology-2021-fgvc8` (`train.csv` avec `image`, `labels` + `train_images/`) | seulement `labels == "healthy"` → SAIN |
| PlantDoc pommier (CC BY 4.0) | API GitHub | `Apple leaf` → SAIN, sinon MALADE ; **test externe uniquement** |
| GYMNSA (CC BY 4.0) | Mendeley, SHA-256 vérifié | label YOLO vide → SAIN, sinon MALADE ; découpage des auteurs conservé (`drone_train` / `drone_val`) |

Paramètres (cellule 1 seulement) : `RUN_MODE` (inventaire | complet), `DOWNLOAD`, `IMG_SIZE` (512), `HARMONIZE_LONG_SIDE` (958), `HARMONIZE_QUALITY` (None = estimée, 75 attendu), `DUP_HAMMING` (4), `SPLIT` (0,70 / 0,15 / 0,15), `FGVC8_MAX_SAINS`, `ATLDSD_MODE` (train | exclure | tout), `LOCAL_DIRS`.

Erreurs remontées : FGVC8 introuvable → arrêt avec la marche à suivre ; AppleLeaf9 introuvable → arrêt ; PlantDoc / GYMNSA indisponibles → avertissement et poursuite sans eux ; empreinte GYMNSA incorrecte → arrêt.

## 3. Sorties (`/kaggle/working/apple_prep`, ou `./apple_prep` en local)
| Fichier | Contenu |
|---|---|
| `cls/{train,val,test}/{SAIN,MALADE}/*.jpg` | jeu principal (AppleLeaf9 + FGVC8 sains), harmonisé, carré `IMG_SIZE` avec bandes grises |
| `cls/test_externe/{SAIN,MALADE}/` | PlantDoc ; jamais utilisé pour entraîner ni régler |
| `drone/cls/{train,val}/{SAIN,MALADE}/`, `drone/det/{train,val}/{images,labels}` + `dataset.yaml` | GYMNSA harmonisé (classe YOLO 0 = malade) |
| `manifest.csv` | une ligne par image : `id, out_path, split, binary, fine, source, sous_source, role, rel, width, height, jpeg_q, md5, dup_cluster, n_boxes` |
| `classes.json` | `{"classes": ["SAIN","MALADE"], "label_mode": "single", "positive_class": "MALADE"}` |
| `effectifs.csv`, `raccourcis_sous_source.csv`, `quarantaine.csv`, `qc/*.jpg`, `README_dataset.md` | contrôles |

`sous_source` ∈ {`fgvc2020`, `fgvc2021`, `atldsd_pvd`, `web`, `drone_poirier`}. Elle est déduite de la taille d'origine pour AppleLeaf9.

## 4. Fonctionnement
1. **Sources** : recherche locale ou dans les Inputs Kaggle, sinon téléchargement (extraction contrôlée contre les chemins `../`).
2. **Inventaire** (`RUN_MODE="inventaire"`) : effectifs, et tailles / qualités JPEG par classe. Rien n'est exporté.
3. **Validation + empreintes** : lecture, taille minimale, md5, 8 empreintes dHash (rotations et miroirs), qualité JPEG estimée.
4. **Doublons** entre toutes les sources feuille. Un conflit d'étiquettes envoie les deux images en quarantaine. Sinon une seule copie est gardée, par priorité : jeu principal > test externe, puis la plus grande image.
5. **Découpage** : 70/15/15 stratifié par (sous-source, classe). ATLDSD va en entraînement seulement (`ATLDSD_MODE="train"`). PlantDoc va en `test_externe`, GYMNSA garde le découpage des auteurs.
6. **Anti-fuite** (assertions bloquantes) : pas de doublon ni de fichier identique entre deux ensembles ; rôles imposés respectés.
7. **Raccourcis** : table sous-source × classe et format d'origine. Alerte si une sous-source évaluée n'a qu'une classe.
8. **Export** avec harmonisation : côté long ≤ 958 px, puis JPEG qualité 75, puis carré `IMG_SIZE` (bandes grises 114). Les tuiles drone passent aussi par le JPEG 75.

## 5. Cohérence avec les autres modules
- **Entrée** : aucun module amont (données publiques). OK.
- **Sortie → notebook 02 + RunLogger (L2)** : les classes `SAIN`, `MALADE` sont des noms valides (ni `,` ni `|`) ; `label_mode` single, `positive_class` MALADE, conforme à L1. Le notebook 02 devra lire `classes.json` et passer les mêmes classes à `RunLogger.start`, et utiliser `manifest.id` comme `ids`, `sous_source` comme `groups`. Il devra aussi rapporter les métriques **par sous-source** et sur `test_externe`.
- **Sortie → pipeline (étape 5)** : le registre prévoit pour `pommier` le type `deux_etages` (détecteur de feuilles, puis classifieur). Ce jeu entraîne **le classifieur** (une feuille → probabilité MALADE). **Écarts ouverts :**
  1. il n'y a aucune donnée ni aucun modèle pour l'**extracteur de feuilles** sur image de drone ;
  2. le classifieur est entraîné sur des images carrées avec bandes grises. Le pipeline (`entree` {largeur, hauteur}) doit appliquer le même letterbox aux feuilles découpées, sinon les feuilles sont déformées. À vérifier ou à ajouter dans le pipeline.

## 6. Test
`python scripts/test_echantillon.py <échantillon_raw> <dossier_de_travail>` fabrique un faux FGVC8 piégé : 4 feuilles saines AppleLeaf9 agrandies en 4000 px, 1 feuille malade étiquetée saine, 1 copie PlantDoc, des lignes `scab` et un fichier absent. Il vérifie que les doublons sont détectés, que le conflit est mis en quarantaine, que la copie est retirée du test externe et que le contrôle anti-fuite passe. Résultat du 30/10/2026 : **TEST OK**.
