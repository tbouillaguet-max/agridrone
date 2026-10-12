# Inventaire des données : olivier

_12 octobre 2026. Projet académique, non commercial : les jeux sous licence non commerciale
ou sans licence sont inclus et téléchargés comme les autres._

Les jeux téléchargeables sont dans le registre
[`configs/data/sources.yaml`](../configs/data/sources.yaml), projet `olive`. Une commande
les récupère tous : `uv run agridrone data download --project olive`. Statut, licence et
attribution de chacun : [`LICENCES_DONNEES.txt`](../LICENCES_DONNEES.txt).

## En bref

- **Niveau parcelle (drone).** Le projet européen **ICAERUS** publie le seul jeu drone
  multispectral d'oliviers avec un état sanitaire par arbre :
  - images brutes DJI Mavic 3M (RVB + vert, rouge, red-edge, PIR), 72 Go ;
  - vignettes par arbre classées en 3 niveaux de symptômes, liés à Xylella.

  Pour la segmentation des houppiers : **SPADE** (orthomosaïques RVB et 4 bandes
  annotées), **OliveTreeSeg** (938 images, masques experts) et **OliveTreeCrownsDb**
  (Maroc).
- **Xylella.** Aucune image drone hyperspectrale ou thermique étiquetée n'est publique.
  Il existe :
  - les vignettes ICAERUS ;
  - une couverture satellite WorldView-2 photo-interprétée (OQDS-Insight) ;
  - 15 362 arbres positifs géolocalisés dans les Pouilles ;
  - des tableaux de traits par arbre (Zarco-Tejada et al. 2018).
- **Feuilles (RVB).** Un seul jeu d'origine pour l'œil de paon et l'acariose : Uğuz et
  Uysal (Turquie, 3 400 photos, sans licence). S'y ajoutent deux jeux d'œil de paon
  (Turquie, Pérou) et un jeu fumagine / virose / carences (Pérou). Aucun jeu public pour
  la tuberculose, la cercosporiose, l'anthracnose sur feuille ni la verticilliose sur
  feuille.
- **Ravageurs.** La **mouche de l'olive** est bien couverte par des images de pièges :
  - McPhail connectés (SmartMcPhail) ;
  - pièges croates (Zadar) ;
  - DIRT (Grèce), en polygones ;
  - comptages McPhail (Leucade) ;
  - pièges jaunes (Portugal), dont le serveur est en panne.

  On trouve aussi la teigne (*Prays oleae*, un export YOLO sans licence) et les mousses
  de cercopes vecteurs de Xylella. Rien pour la cochenille noire, le psylle (hors
  Roboflow), la pyrale ni les thrips.
- **Rien en France.** Aucun jeu d'images d'oliviers de Provence, d'Occitanie ou de Corse.
  Les données françaises de surveillance de Xylella sont des tableaux en accès restreint.
- **Volume.** 33 jeux téléchargeables, environ **137 Go** d'archives (dont 72 Go pour les
  images brutes ICAERUS), plus quelques jeux dont la taille n'est connue qu'au
  téléchargement (Kaggle, git). 7 jeux sont à récupérer à la main (§ 7).

## 1. Méthode

**Recherche.** Huit angles de recherche ont été menés en parallèle par des agents :
- dépôts académiques ;
- Kaggle ;
- Hugging Face, GitHub et Roboflow ;
- littérature 2017-2026 ;
- drone et télédétection ;
- ravageurs ;
- fruits et cultivars ;
- sources participatives (iNaturalist, GBIF, Wikimedia Commons).

Les requêtes étaient en anglais, français, espagnol, italien, portugais et turc. Bilan :
227 candidats, soit **124 jeux distincts**. La vérification croisée par agents s'est
arrêtée deux fois sur la limite d'usage de la session ; elle a été remplacée par une
vérification directe à la source.

**Vérification** (colonne « Vérif. ») :

- ✅✅ **téléchargé ici** : téléchargement, sommes de contrôle et extraction contrôlés de
  bout en bout le 12 octobre (8 jeux) ;
- ✅ **API** : licence, fichiers, tailles et sommes de contrôle lus dans l'API du
  fournisseur (Zenodo, Mendeley, figshare, Dryad, Dataverse, Kaggle), ou dans le dépôt
  GitHub figé sur un commit ;
- 🔎 **agent** : contenu (classes, effectifs, capteur) relevé par un agent de recherche à
  la source, mais non recompté ici.

Les effectifs et les classes des tableaux viennent des agents (🔎) sauf mention
contraire. Licences, tailles et liens sont vérifiés à la source (✅).

**Pertinence pour la vue drone (1 à 5)** : 5 = drone au-dessus d'oliveraies avec
étiquettes utiles ; 1 = laboratoire ou gros plan sans rapport avec la vue drone.

## 2. Niveau parcelle : drone

| Jeu (registre) | Contenu | Capteur, vue | Licence | Taille | Drone | Vérif. |
|---|---|---|---|---|---|---|
| `olive_icaerus_xylella_health` ([zenodo 13120763](https://zenodo.org/records/13120763)) | vignettes RVB et NDVI par arbre, 3 niveaux : asymptomatique / légers / évidents ou dépéri (Xylella). Arbres étiquetés : 3 218 / 702 / 125 + 229. Contient des images augmentées (préfixe `i_`) | DJI Mavic 3M, Italie probable, 25 mai 2024 | CC BY 4.0 | 4,07 Go | 5 | ✅ API · 🔎 effectifs |
| `olive_icaerus_raw_1`, `olive_icaerus_raw_2` ([12943015](https://zenodo.org/records/12943015), [12924461](https://zenodo.org/records/12924461)) | images brutes des mêmes vols : RVB + 4 bandes multispectrales + fichiers de mission ; une archive par vol (8 vols) | DJI Mavic 3M | CC BY 4.0 | 35,6 + 36,1 Go | 5 | ✅ API |
| `olive_icaerus_tree_detection` ([13121962](https://zenodo.org/records/13121962)) | houppiers en boîtes YOLO ; `train_original` sans augmentation | DJI Mavic 3M | CC BY 4.0 | 3,12 Go | 5 | ✅ API |
| `olive_spade_vitafields` ([21510492](https://zenodo.org/records/21510492)) | orthomosaïques RVB et **4 bandes** (18 658×17 429), 21 tuiles annotées (polygones, masques), images brutes, zone irriguée | drone RVB + multispectral, Grèce probable, 2026 | CC BY 4.0 | 15,0 Go | 5 | ✅ API · 🔎 contenu |
| `olive_tree_seg` ([17490916](https://zenodo.org/records/17490916)) | 938 images 4608×3456, masques olivier / fond faits par un expert (655 / 141 / 142) | Parrot Sequoia (RVB), Grèce 2024-2025 | CC BY 4.0 | 3,12 Go | 5 | ✅ API |
| `olive_tree_crowns_db` ([Mendeley xym8rd2srf](https://data.mendeley.com/datasets/xym8rd2srf)) | 46 images en grilles 1×1 à 9×9, boîtes YOLO et VOC, nuage de points, MNT ; 8 070 fichiers | DJI Phantom 4 RTK, 74,7 m, 1,78 cm/px, Meknès | CC BY 4.0 | 1,77 Go | 4 | ✅ API |
| `olive_tree_crowns_multi_crop` ([Mendeley r4w3b2mfnw](https://data.mendeley.com/datasets/r4w3b2mfnw)) | olivier, abricotier, vigne : images et orthomosaïques annotées ; même équipe (recoupement probable) | drone DJI, Maroc | CC BY 4.0 | 1,08 Go | 4 | ✅ API |
| `olive_verticillium_uav` ([zenodo 8144164](https://zenodo.org/records/8144164)) | 3 oliveraies atteintes de verticilliose ; **407 images sans fichier d'annotation** | drone RVB, nord de la Grèce, 2023 | CC BY 4.0 | 4,45 Go | 4 | ✅ API · 🔎 contenu |
| `olive_burned_uav` ([Mendeley 83kpndkrb2](https://data.mendeley.com/datasets/83kpndkrb2)) | 3 624 imagettes : brûlé partiellement, totalement, non brûlé | Phantom 4 PRO / Multispectral RTK, Zenmuse L1, Grèce | CC BY-NC-ND 4.0 | 0,02 Go | 3 | ✅✅ |
| `olive_olea_pred_morocco` ([zenodo 10920137](https://zenodo.org/records/10920137)) | images drone et satellite, positions des arbres, chlorophylle, rendement, sol ; archives RAR | drone + satellite Mohammed VI, Maroc 2024 | CC BY 4.0 | 2,98 Go | 3 | ✅ API |

## 3. Xylella et stress vus d'en haut (satellite, aéroporté, tableaux)

| Jeu (registre) | Contenu | Capteur, vue | Licence | Taille | Drone | Vérif. |
|---|---|---|---|---|---|---|
| `olive_oqds_insight` ([figshare](https://doi.org/10.6084/m9.figshare.28191245.v5)) | environ 77 000 arbres, dont environ 2 200 infectés ou arrachés (photo-interprétation), sur WorldView-2 RVB et NDVI 2019-2021 | satellite, Brindisi | CC BY 4.0 | 2,96 Go | 2 | ✅ API · 🔎 effectifs |
| `olive_xylella_locations_apulia` ([figshare](https://doi.org/10.6084/m9.figshare.22220872.v2)) | 15 362 arbres positifs (protocole officiel UE et EFSA), 2015-2022, coordonnées | tableaux | CC BY 4.0 | < 1 Mo | — | ✅✅ |
| `olive_xf_nplants_2018` ([GitHub Quantalab](https://github.com/Quantalab/Xf-NPlants-2018)) | traits par arbre issus d'images aéroportées hyperspectrales et thermiques, sévérité 0-4, qPCR (Nature Plants 2018) ; sans image | tableaux | MIT | 7 Mo | — | ✅✅ |
| `olive_xylella_ip` ([GitHub](https://github.com/lopsandrea/xylella-ip)) | 238 arbres (78 positifs) : 47 bandes hyperspectrales moyennes + thermique ; sans image | tableaux | GPL-3.0 | < 1 Mo | — | ✅ API |
| `olive_hyperspectral_halkidiki` ([zenodo 10336545](https://zenodo.org/records/10336545)) | 8 cubes hyperspectraux + tableau par arbre (138 bandes) : verticilliose, *Pleospora*, autres stress | Cubert S-185, Chalcidique, mai 2021 | CC BY 4.0 | 7 Mo | 3 | ✅✅ |
| `olive_leaf_dehydration_ms_hs` ([figshare](https://doi.org/10.6084/m9.figshare.26950660.v2)) | feuilles d'avocatier, d'olivier, de vigne : 5 bandes MicaSense, spectres 350-2500 nm, humidité, chlorophylle, azote | laboratoire | CC BY 4.0 | 1,18 Go | 1 | ✅ API |

## 4. Niveau plante : feuilles et arbres en RVB

| Jeu (registre) | Contenu | Vue | Licence | Taille | Drone | Vérif. |
|---|---|---|---|---|---|---|
| `olive_leaf_uguz_uysal` ([GitHub](https://github.com/sinanuguz/CNN_olive_dataset)) | **3 400 photos** en 5 archives : sain 830 (Train1), acariose (*Aculus olearius*) 690 (Train2), train3 423 et train4 777 (dossiers non nommés, œil de paon probable), test 680 (sain 220, Aculus 200, œil de paon 260). Dépôt d'origine, copié sur Kaggle et Roboflow | feuilles, Denizli (Turquie), 2019 | **aucune** | 0,10 Go | 1 | ✅✅ (comptés après extraction) |
| `olive_leaf_peacock_diker` ([Kaggle](https://www.kaggle.com/datasets/serhathoca/zeytin)) | œil de paon : 572 saines, 382 malades (477 prises de vue coupées en deux) ; déposé par un coauteur | feuilles, Turquie 2023 | « Unknown » | 0,74 Go déclarés par Kaggle | 1 | ✅ API · 🔎 effectifs |
| `olive_leaf_peacock_peru` ([Kaggle](https://www.kaggle.com/datasets/antony171060/peacock-spot-detection-in-olive-leaves)) | 680 saines, 680 œil de paon, fond blanc | smartphone, Ilo (Pérou) | CC BY-NC-SA 4.0 | 0,33 Go déclarés par Kaggle | 1 | ✅ API · 🔎 effectifs |
| `olive_leaf_tacna` ([GitHub](https://github.com/ichaparroc/OliveLeafDiseaseDatasetTacna)) | fumagine, virose, carences ; images 224×224 en train / valid / test (774 fichiers) ; pleine résolution sur demande | feuilles, Tacna (Pérou) | **aucune** | 3 Mo | 1 | ✅✅ |
| `olive_leaf_sparkworks` ([GitHub](https://github.com/SparkWorksnet/olive-leaf-dataset)) | 2 566 feuilles, 52 rameaux (fond neutre), 172 arbres vus par drone DJI Mini ; pas d'étiquette sanitaire documentée | mixte | **aucune** | inconnue | 2 | ✅ API (commit figé) |
| `olive_drought_varieties` ([Mendeley 22j26tpk63](https://data.mendeley.com/datasets/22j26tpk63)) | 80 jeunes arbres, 4 régimes d'irrigation (100 à 0 % de l'ETc), 1 440 photos de côté et 1 440 de dessus, mesures hebdomadaires | arbre entier au sol, Fès 2024 | CC BY 4.0 | 9,26 Go | 2 | ✅ API · 🔎 effectifs |

## 5. Ravageurs

| Jeu (registre) | Contenu | Vue | Licence | Taille | Drone | Vérif. |
|---|---|---|---|---|---|---|
| `olive_fly_smartmcphail` ([zenodo 18874302](https://zenodo.org/records/18874302)) | 210 images, 1 348 insectes en boîtes COCO : *B. oleae* femelle, mâle, pyrale | pièges McPhail connectés | CC BY 4.0 | 26 Mo | 1 | ✅✅ |
| `olive_fly_zadar` ([zenodo 21619417](https://zenodo.org/records/21619417)) | pièges découpés en tuiles, boîtes VOC (*B. oleae* et autres insectes) ; environ 4 300 images selon le préprint | pièges, Croatie 2020 | CC BY 4.0 | 0,90 Go | 1 | ✅ API · 🔎 effectifs |
| `olive_fly_dirt_coco` ([zenodo 13992477](https://zenodo.org/records/13992477)) | 291 images DIRT (Grèce, 2018) en polygones COCO ; dépôt cosigné par les auteurs d'origine | pièges McPhail | CC BY 4.0 | 0,12 Go | 1 | ✅ API |
| `olive_fly_digital_mcphail` ([zenodo 21585594](https://zenodo.org/records/21585594)) | 125 images, comptages experts par image (pas de boîtes) | piège McPhail numérique, Leucade 2022 | CC BY 4.0 | 0,42 Go | 1 | ✅ API |
| `olive_spittlebug_db` ([zenodo 17485292](https://zenodo.org/records/17485292)) | 365 images de mousses de cercopes (vecteurs de Xylella), 211 en masques et YOLO ; végétation au sol, pas sur olivier | gros plans, Pouilles 2024-2025 | CC BY 4.0 | 0,94 Go | 1 | ✅ API |
| `olive_prays_oleae_yolo` ([GitHub](https://github.com/Racem-Moalla/prays_oleae_data)) | teigne de l'olivier : export Roboflow, environ 1 035 + 181 images (avec variantes augmentées), une classe ; contexte non documenté | photos WhatsApp, 2022 | **aucune** | 34 Mo | 1 | ✅✅ |

## 6. Fruits

| Jeu (registre) | Contenu | Vue | Licence | Taille | Drone | Vérif. |
|---|---|---|---|---|---|---|
| `olive_fruit_split_v2` ([zenodo 21976264](https://zenodo.org/records/21976264)) | 315 images, **86 790 olives** en boîtes YOLO, mai à novembre 2025 | DJI Mavic 3M rapproché, Tinj (Croatie) | CC BY 4.0 | 2,95 Go | 4 | ✅ API · 🔎 effectifs |
| `olive_fruit_split_tiles` ([zenodo 15746002](https://zenodo.org/records/15746002)) | 1 231 tuiles 640×640, olives à divers stades de maturité | Croatie | CC BY 4.0 | 0,23 Go | 3 | ✅ API |
| `olive_fruit_jaen_uav` ([Kaggle](https://www.kaggle.com/datasets/danielvalyano/olive-fruit-object-detection)) | boîtes YOLOv8 ; 3 411 images dérivées de **27 photos source seulement** | drone, Jaén (Espagne) | CC BY-NC-SA 4.0 | 0,22 Go déclarés par Kaggle | 3 | ✅ API · 🔎 effectifs |
| `olive_fruit_hyperspectral_seville` ([Mendeley 8xvhcsdvst](https://data.mendeley.com/datasets/8xvhcsdvst)) | Manzanilla et Gordal, cubes de 204 bandes, masques des pixels d'olive | SPECIM IQ au sol, Séville | CC BY 4.0 | 10,5 Go | 1 | ✅ API |

## 7. À récupérer à la main ou sur demande

Le registre les liste avec le statut « manuel » : `data download` ne les télécharge pas.

| Jeu | Pourquoi manuel | Licence | Intérêt |
|---|---|---|---|
| Pièges jaunes, mouche de l'olive (IPB, Portugal), [doi:10.34620/dadosipb/NNOPUT](https://doi.org/10.34620/dadosipb/NNOPUT) | le serveur répond « Failed to locate physical file » (HTTP 404) le 12/10 ; réessayer ou écrire à l'IPB | CC0 | élevé (1,42 Go, pièges en oliveraie) |
| Tephritid26, [doi:10.5061/dryad.gf1vhhn36](https://doi.org/10.5061/dryad.gf1vhhn36) | Dryad refuse les téléchargements automatisés : prendre `1022Bactrocera_oleae*.zip` dans le navigateur | CC0 | moyen (spécimens de *B. oleae* en studio, 2,9 Go) |
| Maladies de l'olivier au champ (projet figshare de Bocca) | fichiers hébergés sur mega.nz | CC BY 4.0 | à évaluer (classes non listées) |
| DEEP FARM, cas olivier ([zenodo 17990380](https://zenodo.org/records/17990380)) | accès restreint, demande via Zenodo | CC BY 4.0 | élevé (drone) |
| Haies d'oliviers en multispectral ([zenodo 15743699](https://zenodo.org/records/15743699)) | accès restreint, demande via Zenodo | CC BY 4.0 | élevé (drone multispectral, Cordoue) |
| Roboflow `ezer-rbfrp/pfa-bs1hi` (13 ravageurs et maladies, Tunisie) | compte ou clé Roboflow | CC BY 4.0 déclarée | moyen (provenance à vérifier) |
| Masses cotonneuses du psylle, *Euphyllura olivina* (Velesaca et al. 2025) | Roboflow, compte nécessaire | non vérifiée | moyen (seul jeu de psylle) |

**Sur demande aux auteurs** (articles sans dépôt), d'après la recherche :
- **Drone, maladies et houppiers :**
  - Raouhi et al. 2024 : 14 000 images drone de maladies de l'olivier, Maroc ;
  - Safonova et al. 2021 : houppiers et ombres en multispectral ;
  - Jiménez-Brenes 2017 : taille des arbres, 3D.
- **Mouche de l'olive :**
  - Moreno-Alcaide et al. 2025 : 2 440 images de pièges, Cordoue ;
  - Molina-Rotger et al. 2023 : piège électronique, Majorque.
- **Feuilles et fruits :**
  - MobiRes-Net 2022 : 5 400 feuilles ;
  - OliVaR : noyaux de 131 variétés.
- **Xylella :** Zarco-Tejada et al. 2018, images aéroportées brutes.

## 8. Écartés

| Jeu | Raison |
|---|---|
| Kaggle `habibulbasher01644/olive-leaf-image-dataset` (CC0 déclaré) | copie du jeu d'Uğuz et Uysal sous une autre licence : télécharger l'original |
| Kaggle `erikdervishi/olive-dataset` (« Unknown ») | images DJI du 25 mai 2024, comme les vols ICAERUS : dérivé probable, auteur non identifiable |
| Kaggle `abeersaleh987654321`, `kamarchakroun`, `qingchen987` | compilations d'autres jeux sans provenance par image |
| Hugging Face `Project-AgML/olive_tree_crown_detection` et `spittlebug_segmentation` | copies reformatées d'OliveTreeCrownsDb et de SPITTLEBUG_DB |
| *Good and bad classification of olea europaea* (Mendeley 3gs2kdf4vd) | description générique produite par un robot conversationnel, étiquetage non crédible |
| *Multi-Fruit Leaf Image Dataset* (Mendeley 82vn9k44ky, Bangladesh) | au Bangladesh, « olive » désigne souvent *Elaeocarpus* : espèce douteuse |
| AgiosNikolaos-3 (Kaggle) | arbres urbains, pas des oliveraies |
| msuav500k ([zenodo 16743975](https://zenodo.org/records/16743975), 169 Go) | jeu drone généraliste ; part d'olivier non identifiée |
| Noyaux (zenodo 18789307), AgriLeafNet, 5_olives, microtomographie d'olives | cultivars ou laboratoire, hors du périmètre drone |
| Cartes et statistiques satellitaires (SADIT, Sentinel-2 Chalcidique, carte des vergers d'Italie, phénologie Xylella sous EUPL) | sans image exploitable par les modèles du projet ; à reprendre si besoin |
| Sources participatives (iNaturalist, GBIF, Commons) | 85 à 90 % des photos sous licence NC ou tous droits réservés. En CC0 / CC BY : environ 152 observations de tuberculose, 38 d'œil de paon, 79 de mouche de l'olive. Pas d'olivier pour Xylella ; utilisables seulement en petit test |

## 9. Ce qui n'existe pas en public (recherche du 12 octobre)

- **Aucune image drone hyperspectrale ou thermique d'oliviers avec étiquettes Xylella**
  confirmées en laboratoire. Les campagnes des Pouilles, d'Alicante et de Majorque
  n'existent que sous forme d'articles.
- **Aucun jeu drone thermique de stress hydrique d'olivier.**
- **Aucune verticilliose étiquetée par arbre** : le seul jeu drone n'a pas d'annotation.
- **Aucune image publique** pour :
  - les maladies de la feuille autres que l'œil de paon, l'acariose, la fumagine, la
    virose et les carences : tuberculose, cercosporiose, anthracnose ;
  - plusieurs ravageurs : cochenille noire, pyrale, thrips de l'olivier ;
  - les piqûres de mouche sur fruits ;
  - la maturité des olives (indice 0-7).
- **Aucune donnée d'oliveraie française.**

## 10. Recommandation pour le pipeline olivier

1. **Segmentation drone (niveau parcelle)** :
   - données : OliveTreeSeg (masques experts) et SPADE (orthomosaïque 4 bandes) ;
   - chaîne : celle du blé (U-Net N bandes contre NDVI / NDRE et Otsu), sur les houppiers ;
   - test inter-sources : OliveTreeCrownsDb (Maroc, boîtes seulement).
2. **État sanitaire par arbre** : ICAERUS. Les vignettes RVB et NDVI donnent un
   classifieur à 3 classes. Les images brutes Mavic 3M permettent un modèle multispectral
   par arbre. Écarter les images augmentées (`i_`) des tests.
3. **Feuilles (niveau plante)** : la même méthode que le blé, avec une sortie
   « incertain » et un modèle binaire sain / malade :
   - entraîner sur Uğuz et Uysal (sain, œil de paon, acariose) ;
   - tester sur les jeux d'œil de paon de Turquie (Diker) et du Pérou ;
   - tester sur Tacna comme « maladies jamais vues ».
4. **Mouche de l'olive (détection)** :
   - entraîner sur SmartMcPhail, Zadar et DIRT ;
   - valider les comptages sur le piège McPhail numérique de Leucade.

   Ce chantier ressemble à celui des pucerons, reporté pour le blé.
5. **À demander en priorité** :
   - accès à DEEP FARM et aux haies de Cordoue (drone multispectral) ;
   - réparation du serveur de l'IPB (pièges jaunes) ;
   - les 14 000 images drone de Raouhi et al.

## 11. Reproduire

```bash
uv run agridrone data list --project olive        # statut, licence, taille
uv run agridrone data download --project olive    # tout ce qui est téléchargeable
uv run agridrone data verify                      # sommes de contrôle
```

Les dépôts GitHub de milliers de fichiers sont récupérés avec git, figés sur un commit.
Les dépôts Mendeley de milliers de fichiers sont listés dans
[`configs/data/manifests/`](../configs/data/manifests). Les archives RAR (OLEA-PRED,
feuilles d'Uğuz et Uysal, feuilles en déshydratation) demandent 7-Zip, unar ou bsdtar.
Si un outil échoue, le suivant est essayé.
