# Inventaire et vérification des données (chantier 1)

_Version 2, 7 octobre 2026, refaite après l'ouverture de l'accès internet. Statut : **en
attente de validation**. Aucun téléchargement en masse n'a été fait ; seuls des
métadonnées, des README, des conditions d'utilisation et des articles ont été lus._

## 0. Résumé

- **Pucerons : mis de côté** (ta décision du 7 octobre). La section 2 est conservée telle
  quelle pour plus tard ; le chantier 3 est reporté.
- **Maladies du blé (RVB).** Vérifié directement : le jeu du **John Innes Centre** (999
  images, **CC BY 4.0**, les 4 maladies foliaires majeures + sain) est la meilleure base
  d'entraînement. Pour les tests inter-sources : **ETH Zurich 2026** (CC BY 4.0) et les
  **feuilles d'Éthiopie** (CC BY 4.0). Le jeu complet de John Innes (19 172 images) est
  disponible **sur demande** : c'est la demande la plus utile.
- **Multispectral.** Toujours **aucun jeu public de maladies ou de stress du blé sous
  licence ouverte**. C'est désormais vérifié dans le PDF publié d'Ir-UNet : *« No new data
  were created or analyzed in this study. Data sharing is not applicable to this
  article. »* Pour éprouver la chaîne N bandes, **WeedsGalore** (5 bandes P4M, annotations
  manuelles au pixel, **CC BY 4.0**) remplace WeedMap.
- **Corrections par rapport à la version 1** (licences vérifiées à la source) :
  - **WFD2020** : conditions **non commerciales**, y compris *« testing commercial
    systems »*. Exclu.
  - **WeedMap** : **« In Copyright – Non-Commercial Use Permitted »**. Exclu.
  - **Blé de printemps (Brésil)** : **CC BY-NC 3.0**. Exclu.
- **Clés API** : les secrets ajoutés après le démarrage de la session ne sont pas visibles
  ici (une nouvelle session les verra). Aucun jeu retenu n'en a besoin.

## 1. Méthode

**Niveau de vérification** (colonne « Vérif. ») :

- ✅ **vérifié à la source** : métadonnées DOI (DataCite), API Zenodo ou Kaggle, README ou
  conditions d'utilisation, PDF de l'article lus directement.
- 🔎 **extrait de la page officielle via moteur de recherche** : fiabilité moyenne.
- ❓ **non vérifié** ou introuvable.

**Accès réseau** : ouvert depuis ce jour. Exceptions : le dépôt de l'ETH
(research-collection.ethz.ch) limite le nombre de requêtes (HTTP 429), et MDPI bloque les
accès automatisés (403). Les licences de ces deux sources ont été vérifiées via DataCite.

**Licence et usage commercial futur :**

- **CC BY 4.0 et CC0** : compatibles avec un usage commercial. CC BY impose l'attribution :
  tenir un fichier `ATTRIBUTIONS` par modèle livré.
- **Non commercial** (CC BY-NC, « In Copyright – NC », conditions « recherche ») et licence
  absente ou « Unknown » : **exclus**.

**Pertinence pour la vue drone (1 à 5)** : 5 = même capteur, même culture, vue aérienne ;
1 = laboratoire ou gros plan sans rapport avec la vue drone.

## 2. RVB : pucerons et insectes (mis de côté)

> Section non revérifiée en version 2, conservée pour la reprise du sujet.

| Jeu | Tâche | Images | Annotations | Bandes | Résolution | Licence | Lien | Accessible | Drone 1–5 | Vérif. |
|---|---|---|---|---|---|---|---|---|---|---|
| GreenFlyDB | — | — | — | — | — | — | — | **introuvable** sous ce nom | — | ❓ |
| AID-YOLO | — | — | — | — | — | — | — | **introuvable** ; le nom proche Aphid-YOLO (IEEE TAFE 2025) n'a pas de jeu publié trouvé | — | ❓ |
| APHID-4K (Du et al., *Neurocomputing* 2022) | pucerons du blé au champ | 4 294 | boîtes VOC XML | RVB | 1440×1080 à 4640×3480 | non trouvée | [article](https://www.sciencedirect.com/science/article/abs/pii/S0925231221018506) | aucun lien public | 2 | 🔎 |
| Colonies de pucerons du sorgho (*J. Imaging* 2024) | colonies (≥ 6 pucerons) | 5 447 (→ 54 742 patchs) | masques + boîtes | RVB | 3647×2736 | à confirmer | [doi:10.7910/DVN/N3YJXG](https://doi.org/10.7910/DVN/N3YJXG) | public | 3 | 🔎 |
| Zenodo 7139220 : *Yellow Glue Paper Traps* | aleurodes et pucerons noirs sur pièges | 225 | 5 904 boîtes | RVB | 3840×2160 | CC BY 4.0 | [zenodo 7139220](https://zenodo.org/records/7139220) | public | 1 | 🔎 |
| Zenodo 14097660 : *Black Aphids Glue Paper Traps* | pucerons noirs sur pièges (serre) | 220 | 13 357 boîtes | RVB | — | à confirmer | [zenodo 14097660](https://zenodo.org/records/14097660) | public | 1 | 🔎 |
| AphidCV *Balanced 2k* / *FULL* (Embrapa) | pucerons des céréales en laboratoire | 48 000 / 146 434 | YOLO | RVB | — | CC BY 4.0 / à confirmer | [20138274](https://zenodo.org/records/20138274) · [20145802](https://zenodo.org/records/20145802) | public | 1 | 🔎 |
| Coccinelles du blé (*Data in Brief* 2024) | coccinelles | 2 133 | YOLO | RVB | 640×640 | CC BY-NC 4.0 (à confirmer) | [doi:10.17632/j9735xjspw.1](https://doi.org/10.17632/j9735xjspw.1) | public | 2 | 🔎 |
| IP102 | 102 ravageurs | 75 000+ | classes ; boîtes sur 19 000 | RVB | variable | **aucune licence** | [GitHub](https://github.com/xpwu95/IP102) | Drive / AliyunDrive | 1 | ✅ |
| Roboflow Universe, ex. « Pests » | pucerons / aleurodes / thrips | 2 148 | boîtes | RVB | variable | CC BY 4.0 affiché, provenance inconnue | [Roboflow](https://universe.roboflow.com/samm-v6vxt/pests-wwm0o) | clé API | 1–2 | 🔎 |

## 3. RVB : maladies du blé (et épis)

| Jeu | Tâche | Images | Annotations | Bandes | Résolution | Licence | Lien | Accessible | Drone 1–5 | Vérif. |
|---|---|---|---|---|---|---|---|---|---|---|
| **John Innes Centre** (Long et al., *Plant Pathology* 2023) | classification : sain, rouille jaune, rouille brune, oïdium, septoriose | **999** (jeu complet de 19 172 sur demande) | étiquette par image | RVB | non vérifiée | **CC BY 4.0** | [zenodo 7573133](https://zenodo.org/records/7573133) (zip de 1,03 Go ; mêmes images en PNG : [7307816](https://zenodo.org/records/7307816)) | **oui**, public | 2 | ✅ |
| **ETH Zurich** (Anderegg & McDonald, *Scientific Data* 2026) | séquences quasi quotidiennes de feuilles malades au champ ; masques de symptômes | 12 520 (1 032 séries) | masques, métadonnées (traitements, météo, phénologie) | RVB | ~0,03 mm/px | **CC BY 4.0** | [article](https://www.nature.com/articles/s41597-026-06567-y) · [doi:10.3929/ethz-b-000739194](https://doi.org/10.3929/ethz-b-000739194) | **oui** (taille non vérifiée : dépôt ETH limité en débit) | 1 | ✅ |
| **Feuilles de blé, Éthiopie** (Mendeley) | classification : sain, rouille jaune, septoriose | 407 (102 / 208 / 97) | dossiers par classe | RVB | non vérifiée (Canon EOS 5D Mark III) | **CC BY 4.0** | [doi:10.17632/wgd66f8n6h.1](https://doi.org/10.17632/wgd66f8n6h.1) | **oui**, public | 2 | ✅ licence · 🔎 détails |
| **NWRD** (NUST, *Sensors* 2023) | segmentation de la rouille jaune | 100 | masques binaires PNG | RVB | 6016×4000 et 4608×3456 | **CC BY 4.0** (données) ; MIT (code) | [zenodo 21672928](https://zenodo.org/records/21672928) (zip de 609 Mo) | **oui**, public | 2 | ✅ |
| **GWHD 2021** (épis) | détection d'épis | 6 515 | 275 187 boîtes (CSV) | RVB | non vérifiée | **CC BY 4.0** | [zenodo 5092309](https://zenodo.org/records/5092309) (zip de 10,2 Go) | **oui**, public | 4 | ✅ licence · 🔎 volumes |
| Rouille jaune vue par drone, RVB (2025) | foyers de rouille jaune sur images drone | 12 (6 + 6) | non vérifiées | RVB (drone) | non vérifiée | **CC BY 4.0** | [figshare 29435546](https://doi.org/10.6084/m9.figshare.29435546) (265 Mo) | **oui**, public | 4 | ✅ licence · 🔎 détails |
| Épis fusariés (Univ. Guelph, Dryad 2025) | sévérité de la fusariose par épi | non vérifié | sévérité (Excel) | RVB | non vérifiée | **CC0** | [doi:10.5061/dryad.tht76hf6g](https://doi.org/10.5061/dryad.tht76hf6g) (32,7 Go) | **oui**, public | 1 | ✅ |
| Bangladesh (Mendeley) | point noir, pourriture du pied, sain, helminthosporiose, pyriculariose | 1 603 originales | dossiers par classe | RVB | 1920×1080 | **CC BY 4.0** | [doi:10.17632/5gc7hwydwg.1](https://doi.org/10.17632/5gc7hwydwg.1) | oui | 1 | ✅ licence · 🔎 détails |
| Inde : carence azotée et rouille brune (Mendeley) | 2 sous-jeux de classification | 1 459 | dossiers par classe | RVB (smartphone) | non vérifiée | **CC BY 4.0** | [doi:10.17632/th422bg4yd.1](https://doi.org/10.17632/th422bg4yd.1) | oui | 1 | ✅ licence · 🔎 détails |
| WFD2020 (Genaev et al., *Plants* 2021) | sain, rouille brune, rouille noire, rouille jaune, oïdium, septoriose (multi-étiquettes) | 2 414 (4,84 Go, ~5 Mpx) | 3 147 étiquettes expertes | RVB | ~5 Mpx | **non commercial** + formulaire | [wfd.sysbio.ru](https://wfd.sysbio.ru/) | sur formulaire | 2 | ✅ → **exclu** |
| Yellow-Rust-19 (Hayit et al.) | sévérité de la rouille jaune (6 niveaux) | 15 000 (+ 5 421 brutes) | classe par image | RVB | non vérifiée | **« Unknown »** | [Kaggle](https://www.kaggle.com/datasets/tolgahayit/yellowrust19-yellow-rust-disease-in-wheat) (1,55 Go) | clé Kaggle | 1 | ✅ → **exclu** |
| StripeRust-Pocket (Wuhan University of Technology) | segmentation de la rouille jaune | 542 | masques | RVB (smartphone) | — | **non commercial**, accord signé | [GitHub](https://github.com/WeizhenLiuBioinform/StripeRustNet) | sur accord | 1 | ✅ → **exclu** |
| CGIAR / défi ICLR 2020 (Zindi) | sain, rouille brune, rouille noire | 876 + 610 | étiquette par image | RVB | variable | non vérifiée | [Zindi](https://zindi.africa/competitions/iclr-workshop-challenge-1-cgiar-computer-vision-for-crop-disease) | compte Zindi | 2 | 🔎 → non retenu |
| ETH Zurich (Zenkl et al., 2024/25) | feuille / nécrose / dégâts ; pycnides et pustules | 422 | polygones + points | RVB | haute résolution | non vérifiée | [bioRxiv](https://www.biorxiv.org/content/10.1101/2024.05.10.593608v2) | non vérifié | 1 | 🔎 |
| LWDCD2020 | 10 classes | ~12 000 (≈ 60 % repris d'autres jeux) | — | RVB | — | non trouvée | [article](https://www.sciencedirect.com/science/article/pii/S2352914821001313) | non trouvé | — | 🔎 → **exclu** |
| MSWDD2022 | oïdium, fusariose, jaunisse nanisante, rouille jaune | 2 236 | — | RVB | — | non vérifiée | cité par [Sci. Rep. 2025](https://www.nature.com/articles/s41598-025-33304-z) | non vérifié | 2 | 🔎 |
| FoMo4Wheat (**modèle**, pas un jeu) | backbone ViT pré-entraîné sur 2,5 M images de blé | — | — | RVB | — | **MIT** (code et poids) | [GitHub](https://github.com/PheniX-Lab/FoMo4Wheat) | poids sur Hugging Face | — | ✅ |

## 4. Multispectral

| Jeu | Tâche | Images | Annotations | Bandes | Résolution | Licence | Lien | Accessible | Drone 1–5 | Vérif. |
|---|---|---|---|---|---|---|---|---|---|---|
| Su et al. 2018 (*Comput. Electron. Agric.* 155) | rouille jaune, champ inoculé (2018) | non publié | — | 5 (RedEdge) | 1–1,5 cm/px (16–24 m) | — | [article](https://www.sciencedirect.com/science/article/pii/S0168169918312584) | **non** : aucun dépôt de données | 5 | 🔎 |
| Su et al. 2021 (*IEEE TII*) et Ir-UNet (*Remote Sens.* 2021) | segmentation rouille / sain / fond sur orthomosaïque (2019) | non publié | masques en 3 classes (décrits dans les articles) | 5 (RedEdge) | ~1,3 cm/px (20 m) | — | [Ir-UNet (PDF CC BY)](https://repository.lboro.ac.uk/articles/journal_contribution/Ir-UNet_Irregular_segmentation_U-shape_network_for_wheat_yellow_rust_detection_by_UAV_multispectral_imagery/16699048) | **non** : « Data sharing is not applicable » (Ir-UNet) ; TII annonce un jeu « open-access » sans lien → **demande aux auteurs** | 5 | ✅ |
| Nguyen et al. 2023 (*Remote Sens.* 15:3301) | rouille jaune par micro-parcelle : sain / légère / sévère + rendement | 700 parcelles (592 notées) | une classe par parcelle | 5 (DJI P4 Multispectral) | 1,04 cm/px (20 m) | — | [manuscrit](https://par.nsf.gov/servlets/purl/10466254) | **sur demande** → **demande aux auteurs** | 5 | ✅ protocole · 🔎 accès |
| RustQNet (*Comput. Electron. Agric.* 2024) | indice de rouille jaune, multitemporel RVB + MS | « > 180 M pixels annotés » | — | RVB + MS | — | — | [article](https://www.sciencedirect.com/science/article/abs/pii/S0168169924006367) | non vérifié | 5 | 🔎 |
| Blasch et al. 2023 (*Sci. Rep.*), CIMMYT Éthiopie | rouilles jaune et noire, drone + satellite | — | — | MS | — | — | [article](https://www.nature.com/articles/s41598-023-43770-y) | non vérifié | 4 | 🔎 |
| **WeedsGalore** (GFZ Potsdam, WACV 2025) | segmentation maïs / 4 classes d'adventices (sémantique + instances), multitemporel | ~1 150 prises de vue ; recadrages annotés de 600×600 sur 48 emplacements | **masques manuels** | 5 (DJI P4 Multispectral : B, V, R, RE, PIR) | **2,5 mm/px** (vol à 5 m) | **CC BY 4.0** (données) ; Apache-2.0 (code) | [GitHub](https://github.com/GFZ/weedsgalore) · [données](https://doidata.gfz.de/weedsgalore_e_celikkan_2024/) (321 Mo + orthomosaïques 11 Go) | **oui**, testé (listing) | 3 | ✅ |
| Maïs, stress hydrique et rouille commune (Turquie 2025) | sol / sain / stress hydrique faible / fort / rouille | patchs + orthomosaïques sources | **pseudo-masques dérivés d'indices** | 5 + alpha (P4M ; ordre B, V, R, RE, PIR) | vol à 15 m (extrait de recherche) | **CC BY 4.0** | [zenodo 22062459](https://zenodo.org/records/22062459) (v2.1, 1,39 Go) | **oui**, public | 3 | ✅ |
| Kazakhstan, blé / soja / orge (*Data* 2023) | type de culture (aucune étiquette maladie) | 5 vols sur 27 parcelles de 1 ha (2022) | type de culture | 5 + NDVI (DJI Phantom 4 MS) | 3 cm | **CC BY 4.0** | [zenodo 7860751](https://zenodo.org/records/7860751) (23,3 Go) | **oui**, public | 3 | ✅ |
| Agriculture-Vision (CVPR 2020, défi 2021) | 9 anomalies de parcelle (maïs, soja) | 94 986 tuiles 512×512 | masques | 4 (R, V, B, PIR), 8 bits normalisés | 10 à 20 cm/px | **non commercial** | [S3](https://intelinair-data-releases.s3.amazonaws.com/?prefix=agriculture-vision/&delimiter=/) | oui (21,0 Go) | 3 | ✅ → **exclu** |
| WeedMap (ETH ASL 2018) | fond / culture / adventice (betterave) | 18 746 fichiers (~5,36 Go) | masques | RedEdge-M (5) + Sequoia (4) | — | **« In Copyright – Non-Commercial Use Permitted »** | [doi:10.3929/ethz-c-000788571](https://doi.org/10.3929/ethz-c-000788571) | oui | 3 | ✅ → **exclu** |
| Blé de printemps, Brésil (Mendeley) | biomasse par parcelle | — | biomasse | 4 (Sequoia) | 4,65 cm (50 m) | **CC BY-NC 3.0** | [doi:10.17632/jzh4x3svv5.2](https://doi.org/10.17632/jzh4x3svv5.2) | oui | 3 | ✅ → **exclu** |

## 5. Fiches : conditions de prise de vue et remarques

### 5.1 Maladies du blé

- **John Innes Centre (Norwich, Royaume-Uni).** D'après la fiche Zenodo : *« 999 wheat
  disease images, including yellow rust, brown rust, septoria, mildew and healthy leaves
  taken in realistic growth conditions »*, au champ et en serre selon l'article. Ce sont
  exactement les maladies foliaires majeures du blé tendre en France. La fiche indique que
  le jeu complet (19 172 images) est *« available on request »* auprès de James Brown.
- **ETH Zurich 2026.** Feuilles suivies quasi quotidiennement au champ à Lindau-Eschikon
  (Suisse), saisons 2022–2023 et 2023–2024, à ~0,03 mm/px. Climat proche de la France,
  septoriose et rouilles. Très bon jeu de **test inter-sources**. Il faudra vérifier au
  chantier 2 comment ses étiquettes (masques et métadonnées d'occurrence) se ramènent à
  nos classes.
- **Éthiopie (Holeta).** Feuilles au champ, appareil reflex, conditions non contrôlées. Il
  partage 3 classes avec John Innes (sain, rouille jaune, septoriose) : c'est l'écart de
  domaine le plus simple à mesurer.
- **NWRD.** Images multi-feuilles au champ (NUST, Pakistan), masques de rouille jaune.
  Petit (100 images), mais annoté au pixel.
- **GWHD 2021.** Couvert vu du dessus, 12 pays. Base de référence pour détecter les épis,
  avant toute classification au niveau de l'épi.
- **Exclus :** WFD2020 (conditions non commerciales, vérifiées sur le site), Yellow-Rust-19
  (« Unknown », vérifié via l'API Kaggle), StripeRust-Pocket (accord non commercial),
  LWDCD2020 (introuvable, provenance mixte). **Peu pertinents** pour la France :
  Bangladesh, Inde.

### 5.2 Multispectral

- **Su et al. / Ir-UNet (vérifié dans le PDF publié).** Station de Caoxinzhuang (Northwest
  A&F University, Yangling, Chine), cultivar sensible Xiaoyan 22. 18 micro-parcelles de
  2 m × 2 m inoculées à 6 niveaux, vol du 2 mai 2019 à ~20 m (~1,3 cm/px). Caméra
  MicaSense RedEdge, avec panneau de calibration avant chaque vol. Étiquettes en 3 classes
  (rouille, sain, fond), tracées d'après des photos RVB prises à 2 m et un seuil OSAVI.
  **Ce jeu correspond exactement à la cible, mais il n'est publié nulle part.**
- **Nguyen et al. 2023 (vérifié dans le manuscrit).** Chacabuco (Argentine), blé de
  printemps 2021, 700 micro-parcelles de 1,2 × 5 m, DJI P4 Multispectral à 20 m
  (1,04 cm/px). Notes sain / infection légère / sévère sur 592 parcelles, et rendement par
  parcelle. Étiquettes **par parcelle**, pas par pixel. Partenaire industriel (GDM Seeds) :
  l'accès commercial peut être restreint.
- **WeedsGalore (vérifié).** DJI P4 Multispectral (B 450 ± 16 nm, V 560 ± 16, R 650 ± 16,
  RE 730 ± 16, PIR 840 ± 26), vol à 5 m (2,5 mm/px), champ expérimental près de Potsdam
  (Allemagne). Les annotations portent sur les images brutes alignées, pas sur
  l'orthomosaïque. Autre tâche (adventices), mais une vraie vérité terrain manuelle sur 5
  bandes et une licence ouverte.
- **Maïs, Turquie.** La version 2.1 corrige une inversion des bandes 4 et 5 (RE / PIR) et a
  régénéré ses pseudo-masques. Les patchs sont normalisés par canal (percentiles 2–98) :
  **ce n'est pas de la réflectance**. Les masques étant dérivés d'indices, ce jeu ne peut
  pas servir à comparer un U-Net à une baseline par indices.
- **Point d'attention pour le code N bandes.** L'ordre des bandes diffère d'un capteur à
  l'autre. MicaSense RedEdge range ses bandes B, V, R, **PIR, RE** (tableau 1 d'Ir-UNet) ;
  la DJI P4M les range B, V, R, **RE, PIR**. Les longueurs d'onde diffèrent aussi (rouge à
  668 nm contre 650 nm). Chaque bande sera donc nommée explicitement dans une
  configuration par capteur, sans jamais supposer un ordre.

## 6. Vue drone : rappel sur la résolution au sol

Résolution au sol : `GSD = H × l / (f × N)`, avec H la hauteur au-dessus du couvert, l la
largeur du capteur, f la focale et N la largeur de l'image en pixels. Exemple avec un
capteur plein format (36 mm, 8192 px, focale 35 mm) : 0,25 mm/px à 2 m, 0,63 mm/px à 5 m,
1,26 mm/px à 10 m. Les jeux « maladies » publics sont des gros plans de feuilles, bien plus
fins que ce qu'un drone obtient à hauteur de travail. L'écart de domaine sera mesuré au
chantier 4 (entraînement sur une source, test sur une autre). Pour les pucerons (mis de
côté), ce calcul impose un vol à environ 2 m pour voir des individus.

## 7. Recommandation

### 7.1 Chantier 4 : classification des maladies

- **Classes** : sain, rouille jaune, rouille brune, septoriose, oïdium, plus une sortie
  « incertain ».
- **Entraînement** : John Innes, 999 images (CC BY 4.0). Si la demande aboutit, le jeu
  complet de 19 172 images.
- **Tests inter-sources** : Éthiopie (3 classes communes) et ETH Zurich 2026.
- **Backbones** : EfficientNet-B0 et ConvNeXt-Tiny (timm), plus en option FoMo4Wheat
  ViT-B/14 (MIT, pré-entraîné sur du blé).
- **Plus tard** : GWHD 2021 pour les épis ; NWRD pour segmenter la rouille jaune.

### 7.2 Chantier 5 : multispectral (alternative)

1. Construire la chaîne N bandes et la baseline par indices (NDVI, NDRE, Otsu).
2. La valider sur **WeedsGalore** : vraie vérité terrain, 5 bandes, CC BY 4.0.
3. Utiliser le jeu maïs **uniquement** comme test de lecture des données.
4. Demander les données de Su et al. et de Nguyen et al.
5. Préparer le protocole de collecte drone.

### 7.3 Volume à télécharger au chantier 2 (si validé)

| Jeu | Taille | Rôle |
|---|---|---|
| John Innes (999) | 1,03 Go | entraînement chantier 4 |
| Éthiopie | non vérifiée (petit) | test chantier 4 |
| ETH Zurich 2026 | non vérifiée | test chantier 4 |
| WeedsGalore (jeu annoté) | 321 Mo | validation chantier 5 |
| Maïs, Turquie | 1,39 Go | test de lecture chantier 5 |

Total connu : environ 2,7 Go, plus les deux tailles non vérifiées. GWHD (10,2 Go), les
orthomosaïques WeedsGalore (11 Go) et Kazakhstan (23,3 Go) ne seront téléchargés que si
une étape en a besoin.

## 8. Demandes aux auteurs

Voir [`reports/data_requests.md`](data_requests.md) : objet, intérêt et brouillon de mail
pour chaque demande (John Innes ; Su et al. ; Nguyen et al.).

## 9. Sources principales

- Licences vérifiées via DataCite (`api.datacite.org/dois/<doi>`) et l'API Zenodo
  (`zenodo.org/api/records/<id>`), consultées le 7 octobre 2026.
- [Ir-UNet, PDF publié](https://repository.lboro.ac.uk/articles/journal_contribution/Ir-UNet_Irregular_segmentation_U-shape_network_for_wheat_yellow_rust_detection_by_UAV_multispectral_imagery/16699048) ;
  [Su et al. 2021, manuscrit](https://repository.essex.ac.uk/27051/8/ALL_TII-19-5199.pdf) ;
  [Nguyen et al. 2023, manuscrit](https://par.nsf.gov/servlets/purl/10466254).
- [Conditions WFD2020](https://wfd.sysbio.ru/datasets-terms-and-conditions.html) ;
  [accord StripeRust-Pocket](https://github.com/WeizhenLiuBioinform/StripeRustNet) ;
  conditions Agriculture-Vision (PDF dans le bucket S3).
- [WeedsGalore : article](https://arxiv.org/abs/2502.13103), [dépôt](https://github.com/GFZ/weedsgalore),
  [données](https://doidata.gfz.de/weedsgalore_e_celikkan_2024/).
- [John Innes, Zenodo](https://zenodo.org/records/7573133) ; [ETH 2026](https://www.nature.com/articles/s41597-026-06567-y) ;
  [GWHD 2021](https://zenodo.org/records/5092309) ; [NWRD](https://zenodo.org/records/21672928) ;
  [maïs, Turquie](https://zenodo.org/records/22062459) ; [Kazakhstan](https://zenodo.org/records/7860751).
- Revue des jeux multispectraux drone (39 jeux) : [Remote Sens. 2026](https://doi.org/10.3390/rs18040659).
