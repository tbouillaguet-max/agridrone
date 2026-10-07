# Inventaire et vérification des données (chantier 1)

_7 octobre 2026. Statut : **en attente de validation**. Aucun téléchargement en masse
n'a été fait ; seuls quelques fichiers de métadonnées (conditions d'utilisation, README,
article) ont été lus._

## 0. Résumé

- **Pucerons (RVB).** Aucun jeu public ne montre de pucerons sur blé **vus depuis un
  drone**. Le plus proche du besoin, APHID-4K (4 294 images de pucerons du blé au champ),
  n'a pas de lien de téléchargement trouvé. Le meilleur candidat accessible est le jeu
  « colonies de pucerons du sorgho » (Harvard Dataverse, 5 447 images de terrain prises à
  3 hauteurs), avec une licence à confirmer. **GreenFlyDB et AID-YOLO sont introuvables**
  sous ces noms. Zenodo 7139220 (pièges collants) : pré-entraînement au mieux.
- **Maladies du blé (RVB).** Il existe des jeux sérieux, mais tous en **gros plan** (feuilles
  photographiées à la main). À retenir : John Innes Centre (Royaume-Uni, maladies
  pertinentes en France), WFD2020, ETH Zurich 2026 (12 520 images, Suisse), feuilles
  d'Éthiopie (CC BY 4.0), NWRD ; GWHD 2021 pour détecter les épis. Écartés pour leur
  licence : Yellow-Rust-19 (« Unknown »), StripeRust-Pocket (non commercial).
- **Multispectral.** **Aucun jeu public, vérifié et sous licence ouverte de maladies ou de
  stress du blé** n'a été trouvé. Les données de Su et al. 2018 et d'Ir-UNet (Zhang et al.
  2021) ne sont pas téléchargeables. La déclaration de disponibilité d'Ir-UNet indique :
  *« No new data were created or analyzed in this study. Data sharing is not applicable »*.
  Agriculture-Vision est vérifié **non commercial**, donc exclu. Conséquence de ta règle :
  le chantier 5 ne peut pas entraîner une segmentation « zones malades / stressées du blé »
  sur données publiques. Je propose une alternative au §7.3.
- **Hypothèse à revoir.** Détecter des pucerons **individuels** demande une résolution au
  sol d'environ 0,25 mm/px, soit un vol à environ 2 m avec un capteur plein format (calcul
  au §6). À 10 m, un puceron couvre 1 à 2 pixels. Il faut viser les **colonies et les épis
  infestés** à très basse altitude, et lancer tôt la collecte d'un jeu drone propre.
- **Limites de la vérification.** Le réseau de cet environnement bloque Zenodo, Mendeley,
  Kaggle, Roboflow, Figshare, Dataverse, Dryad, Hugging Face et les sites des éditeurs.
  Vérifiés directement : Agriculture-Vision (bucket S3, conditions d'utilisation et article
  lus) et les dépôts GitHub. Le reste provient d'extraits des pages officielles obtenus par
  moteur de recherche (niveau 🔎). Licence et sommes de contrôle seront revérifiées
  automatiquement au téléchargement (chantier 2).

## 1. Méthode

**Niveau de vérification** (colonne « Vérif. ») :

- ✅ **vérifié à la source** : fichier ou page lus directement.
- 🔎 **extrait de la page officielle via moteur de recherche** : page non ouverte
  directement car l'hôte est bloqué. Fiabilité moyenne, à reconfirmer au téléchargement.
- ❓ **non vérifié** ou introuvable.

**Accès réseau depuis l'environnement de travail.** Bloqués (refus du proxy) : zenodo.org,
data.mendeley.com, www.kaggle.com, universe.roboflow.com, api.roboflow.com, figshare.com,
huggingface.co, dataverse.harvard.edu, datadryad.org, www.research-collection.ethz.ch,
wfd.sysbio.ru, download.pytorch.org, ainsi que les sites des éditeurs (MDPI, ScienceDirect,
PMC, arXiv). Accessibles : PyPI, GitHub (code, fichiers bruts, releases), Amazon S3,
Google Cloud Storage. La colonne « Accessible » distingue donc « testé ici » de « public
d'après la page (non testé ici) ».

**Licence et usage commercial futur :**

- **CC BY 4.0 et CC0** : compatibles avec un usage commercial. CC BY impose l'attribution :
  tenir un fichier `ATTRIBUTIONS` par modèle livré.
- **CC BY-NC, « recherche non commerciale », licence absente ou « Unknown »** : **exclus**
  pour un produit commercial. Sans licence, tous les droits restent réservés par défaut.
- **Roboflow Universe** : la licence affichée est choisie par le déposant, qui n'est pas
  toujours l'auteur des images. Il faut une provenance documentée.

**Pertinence pour la vue drone (1 à 5)** : 5 = même capteur, même culture, vue aérienne ;
1 = laboratoire, piège ou gros plan sans rapport avec la vue drone.

## 2. RVB : pucerons et insectes

| Jeu | Tâche | Images | Annotations | Bandes | Résolution | Licence | Lien | Accessible | Drone 1–5 | Vérif. |
|---|---|---|---|---|---|---|---|---|---|---|
| GreenFlyDB | — | — | — | — | — | — | — | **introuvable** (aucun résultat sous ce nom, plusieurs requêtes) | — | ❓ |
| AID-YOLO (pucerons du blé) | — | — | — | — | — | — | — | **introuvable** ; le nom proche Aphid-YOLO (IEEE TAFE 2025) n'a pas de jeu publié trouvé | — | ❓ |
| APHID-4K (Du et al., *Neurocomputing* 2022) | détection de pucerons du blé au champ | 4 294 | boîtes, VOC XML ; ~12,6 pucerons/image | RVB | 1440×1080 à 4640×3480 | non trouvée | [article](https://www.sciencedirect.com/science/article/abs/pii/S0925231221018506) | **non** : aucun lien public, à demander aux auteurs | 2 | 🔎 |
| Colonies de pucerons du sorgho (Rahman et al., *J. Imaging* 2024) | détection et segmentation de colonies (≥ 6 pucerons) | 5 447 (→ 54 742 patchs multi-échelles) | masques + boîtes dérivées | RVB | 3647×2736 | **à confirmer** (CC0 par défaut sur Dataverse, non vérifié) | [doi:10.7910/DVN/N3YJXG](https://doi.org/10.7910/DVN/N3YJXG) | oui, public (non testé ici) | 3 | 🔎 |
| Zenodo 7139220 : *Yellow Glue Paper Traps* | détection d'aleurodes et de pucerons noirs sur pièges jaunes | 225 | 5 904 boîtes (2 431 aleurodes, 3 473 pucerons noirs), annotées avec Roboflow | RVB | 3840×2160 | CC BY 4.0 | [zenodo 7139220](https://zenodo.org/records/7139220) | oui, public (non testé ici) | 1 | 🔎 |
| Zenodo 14097660 : *Black Aphids Glue Paper Traps* | détection de pucerons noirs sur pièges (serre de concombre) | 220 | 13 357 boîtes (Roboflow), découpage 175/45 | RVB | non vérifiée | **non vérifiée** | [zenodo 14097660](https://zenodo.org/records/14097660) | oui, public (non testé ici) | 1 | 🔎 |
| AphidCV *Balanced 2k* (UPF / Embrapa, 2026) | pucerons ailés, aptères, nymphes, « faux » ; 6 espèces dont 4 des céréales | 48 000 | YOLO, découpage 80/20 | RVB | non vérifiée | CC BY 4.0 | [zenodo 20138274](https://zenodo.org/records/20138274) | oui, public (non testé ici) | 1 | 🔎 |
| AphidCV *FULL* | idem | 146 434 | idem | RVB | non vérifiée | **non vérifiée** | [zenodo 20145802](https://zenodo.org/records/20145802) | oui, public (non testé ici) | 1 | 🔎 |
| Coccinelles du blé (Grijalva et al., *Data in Brief* 2024) | détection de coccinelles (auxiliaires) au champ | 2 133 | boîtes YOLO (.txt) | RVB | 640×640 | **CC BY-NC 4.0** (à confirmer) | [doi:10.17632/j9735xjspw.1](https://doi.org/10.17632/j9735xjspw.1) | oui, public | 2 | 🔎 |
| IP102 | classification (102 ravageurs) ; détection sur 19 000 images | 75 000+ | classes ; boîtes | RVB | variable | **aucune licence** dans le dépôt | [GitHub](https://github.com/xpwu95/IP102) | Google Drive / AliyunDrive | 1 | ✅ |
| *Aphid Image Dataset Based on Natural Background* (Anhui, revue AgBigData) | 13 espèces de pucerons au champ | 6 287 | non vérifiées (classification d'après le résumé) | RVB (reflex) | non vérifiée | non vérifiée | [résumé](http://agbigdata.aiijournal.com/EN/abstract/abstract23065.shtml) | non vérifié | 2 | 🔎 |
| Roboflow Universe, ex. « Pests » (samm-v6vxt) | détection pucerons / aleurodes / thrips | 2 148 | boîtes | RVB | variable | CC BY 4.0 **affiché** (provenance inconnue) | [Roboflow](https://universe.roboflow.com/samm-v6vxt/pests-wwm0o) | clé API Roboflow | 1–2 | 🔎 |

Autres jeux repérés mais non retenus (domaine trop éloigné ou disponibilité inconnue) :
[pucerons du pois en laboratoire](https://zenodo.org/records/10811254) (Zenodo 10811254),
[LeLePhid](https://data.mendeley.com/datasets/tndhs2zng4/1) (feuilles de citronnier, 665 images),
[AphColDat](https://www.sciencedirect.com/science/article/abs/pii/S016816992200895X) (colonies
sur Brassica, 376 images, disponibilité non trouvée).

## 3. RVB : maladies du blé (et épis)

| Jeu | Tâche | Images | Annotations | Bandes | Résolution | Licence | Lien | Accessible | Drone 1–5 | Vérif. |
|---|---|---|---|---|---|---|---|---|---|---|
| John Innes Centre (Long et al., *Plant Pathology* 2023), sous-ensemble public | classification : sain, rouille jaune, rouille brune, oïdium, septoriose | 999 (jeu complet de 19 172 sur demande) | étiquette par image | RVB | non vérifiée | **à confirmer** (accès « Open ») | [zenodo 7573133](https://zenodo.org/records/7573133) | oui pour les 999 (non testé ici) ; jeu complet sur demande | 2 | 🔎 |
| WFD2020 (Genaev et al., *Plants* 2021) | classification : sain, rouille brune, rouille noire, rouille jaune, oïdium, septoriose | 2 414 | étiquetage expert (CSV) | RVB | non vérifiée | **à confirmer** : CC BY 4.0 selon un extrait, non confirmé par un second | [wfd.sysbio.ru](http://wfd.sysbio.ru/) | oui d'après le site (zip + CSV), non testé ici | 2 | 🔎 |
| ETH Zurich (Anderegg & McDonald, *Scientific Data* 2026) | séquences quasi quotidiennes de feuilles malades au champ ; masques de symptômes | 12 520 (1 032 séries) | masques de segmentation, métadonnées (traitements, météo, phénologie) | RVB | ~0,03 mm/px | CC BY 4.0 selon l'article (licence du dépôt à confirmer) | [article](https://www.nature.com/articles/s41597-026-06567-y) · données : doi:10.3929/ethz-b-000739194 | oui, public (non testé ici) | 1 | 🔎 |
| ETH Zurich (Zenkl et al., *Comput. Electron. Agric.* 2024/25) | segmentation feuille / nécrose / dégâts d'insectes ; points (pycnides, pustules) | 422 | polygones + points | RVB | « haute résolution » | non vérifiée | [bioRxiv](https://www.biorxiv.org/content/10.1101/2024.05.10.593608v2) | non vérifié | 1 | 🔎 |
| NWRD (NUST, *Sensors* 2023) | segmentation de la rouille jaune | 100 | masques binaires PNG | RVB | 6016×4000 et 4608×3456 | données : CC BY 4.0 selon l'article (non vérifié) ; code : MIT ✅ | [GitHub](https://github.com/dll-ncai/NUST-Wheat-Rust-Disease-NWRD) · [zenodo 21672928](https://zenodo.org/records/21672928) | oui (non testé ici) | 2 | ✅ / 🔎 |
| Feuilles de blé, Éthiopie (Mendeley wgd66f8n6h) | classification : sain, rouille jaune, septoriose | 407 (208 / 102 / 97) | dossiers par classe | RVB | non vérifiée (Canon EOS 5D Mark III) | CC BY 4.0 | [Mendeley](https://data.mendeley.com/datasets/wgd66f8n6h/1) | oui, public (non testé ici) | 2 | 🔎 |
| CGIAR / défi ICLR 2020 (Zindi) | classification : sain, rouille brune, rouille noire | 876 (entraînement) + 610 (test) | étiquette par image | RVB | variable | **non vérifiée** | [Zindi](https://zindi.africa/competitions/iclr-workshop-challenge-1-cgiar-computer-vision-for-crop-disease) | compte Zindi + acceptation du règlement | 2 | 🔎 |
| Yellow-Rust-19 (Hayit et al.) | sévérité de la rouille jaune (0, R, MR, MRMS, MS, S) | 15 000 (+ 5 421 brutes) | classe par image | RVB | non vérifiée | **« Unknown » sur Kaggle** | [Kaggle](https://www.kaggle.com/datasets/tolgahayit/yellowrust19-yellow-rust-disease-in-wheat) | clé Kaggle | 1 | 🔎 |
| StripeRust-Pocket (Wuhan University of Technology) | segmentation de la rouille jaune (fond / sain / malade) | 542 | masques | RVB (smartphone) | non vérifiée | **non commercial**, accord à signer | [GitHub](https://github.com/WeizhenLiuBioinform/StripeRustNet) | sur accord signé | 1 | ✅ |
| LWDCD2020 (Goyal et al.) | classification en 10 classes | ~12 000 (≈ 40 % prises au champ, le reste repris d'autres jeux) | étiquette par image | RVB | non vérifiée | non trouvée | [article](https://www.sciencedirect.com/science/article/pii/S2352914821001313) | **non trouvé** | — | 🔎 |
| Bangladesh (Mendeley 5gc7hwydwg) | classification : point noir, pourriture du pied, sain, helminthosporiose, pyriculariose | 1 603 originales | dossiers par classe | RVB | 1920×1080 | CC BY 4.0 | [Mendeley](https://data.mendeley.com/datasets/5gc7hwydwg/1) | oui, public (non testé ici) | 1 | 🔎 |
| Inde : carence azotée et rouille brune (Mendeley th422bg4yd) | classification (2 sous-jeux) | 1 459 | dossiers par classe | RVB (smartphone) | non vérifiée | CC BY 4.0 | [Mendeley](https://data.mendeley.com/datasets/th422bg4yd/1) | oui, public (non testé ici) | 1 | 🔎 |
| MSWDD2022 | classification : oïdium, fusariose, jaunisse nanisante, rouille jaune | 2 236 | étiquette par image | RVB | non vérifiée | non vérifiée | cité par [Sci. Rep. 2025](https://www.nature.com/articles/s41598-025-33304-z) | non vérifié | 2 | 🔎 |
| Rouille jaune vue par drone, RVB (figshare 29435546) | foyers de rouille jaune sur images drone | 12 (6 + 6) | non vérifiées | RVB (drone) | non vérifiée | CC BY 4.0 | [figshare](https://doi.org/10.6084/m9.figshare.29435546) | oui (non testé ici) | 4 | 🔎 |
| GWHD 2021 (épis) | détection d'épis | 6 515 | 275 187 boîtes | RVB | non vérifiée | CC BY 4.0 | [doi:10.5281/zenodo.5092309](https://doi.org/10.5281/zenodo.5092309) | oui (non testé ici) | 4 | 🔎 |
| Épis fusariés (Univ. Guelph, Dryad 2025) | sévérité de la fusariose par épi | non vérifié (base d'images de 32,69 Go) | sévérité (Excel) | RVB | non vérifiée | CC0 (politique de Dryad, à confirmer) | [doi:10.5061/dryad.tht76hf6g](https://doi.org/10.5061/dryad.tht76hf6g) | oui (non testé ici) | 1 | 🔎 |
| FoMo4Wheat (**modèle**, pas un jeu) | backbone ViT pré-entraîné sur ImAg4Wheat (2,5 M images de blé) | — | — | RVB | — | **MIT (code et poids)** ; ImAg4Wheat complet « publié à la parution de l'article » | [GitHub](https://github.com/PheniX-Lab/FoMo4Wheat) | poids sur Hugging Face | — | ✅ |

## 4. Multispectral

| Jeu | Tâche | Images | Annotations | Bandes | Résolution | Licence | Lien | Accessible | Drone 1–5 | Vérif. |
|---|---|---|---|---|---|---|---|---|---|---|
| Su et al. 2018 (*Comput. Electron. Agric.* 155) : rouille jaune, RedEdge | rouille jaune sur champ inoculé | non publié | — | 5 (B, V, R, RE, PIR) | 1–1,5 cm/px (16–24 m) | — | [article](https://www.sciencedirect.com/science/article/pii/S0168169918312584) | **non** : aucun lien de données trouvé | 5 | 🔎 |
| Su et al. 2021 (*IEEE TII*) / Ir-UNet (Zhang et al., *Remote Sens.* 2021) | segmentation de la rouille jaune sur orthomosaïque RedEdge (DJI M100) | non publié | — | 5 | non vérifiée | — | [Ir-UNet](https://doi.org/10.3390/rs13193892) · TII : doi:10.1109/TII.2020.2979237 | **non** : déclaration Ir-UNet « Data sharing is not applicable » | 5 | 🔎 |
| Nguyen et al. 2023 (*Remote Sens.* 15:3301) | détection précoce de la rouille jaune (P4M, Argentine, 2021) | — | — | 5 | non vérifiée | — | [article](https://doi.org/10.3390/rs15133301) | **sur demande** aux auteurs | 5 | 🔎 |
| RustQNet (*Comput. Electron. Agric.* 2024) | inversion de l'indice de rouille jaune, multitemporel RVB + MS | « > 180 M pixels annotés » | — | RVB + MS | non vérifiée | — | [article](https://www.sciencedirect.com/science/article/abs/pii/S0168169924006367) | non vérifié (aucun lien trouvé) | 5 | 🔎 |
| Blasch et al. 2023 (*Sci. Rep.*) : CIMMYT, Éthiopie | rouilles jaune et noire, drone + satellite | — | — | MS | non vérifiée | — | [article](https://www.nature.com/articles/s41598-023-43770-y) | non vérifié | 4 | 🔎 |
| Dakota du Sud 2025 (*Smart Agric. Technol.*) | sévérité de la bactériose à stries (BLS) et de la fusariose par micro-parcelle | — | notes par parcelle | MS | non vérifiée | — | [article](https://www.sciencedirect.com/science/article/pii/S2772375525009608) | non vérifié | 4 | 🔎 |
| Agriculture-Vision (CVPR 2020, défi 2021) | segmentation de 9 anomalies de parcelle (maïs, soja ; Midwest) | 94 986 tuiles 512×512 (version 2020) | masques | 4 (R, V, B, PIR), valeurs 8 bits normalisées, **pas de réflectance** | 10, 15 ou 20 cm/px | **non commercial** | [bucket S3](https://intelinair-data-releases.s3.amazonaws.com/?prefix=agriculture-vision/&delimiter=/) · [article](https://arxiv.org/abs/2001.01306) | **oui, testé ici** (bucket listé ; archive 2021 de 21,0 Go) | 3 | ✅ |
| Maïs, stress hydrique et rouille commune (Turquie 2025, Zenodo 22062459) | segmentation : sol, sain, stress hydrique faible / fort, rouille | 592 pour le sous-jeu stress hydrique ; total non vérifié | **pseudo-masques dérivés d'indices de végétation** | 5 + alpha (B, V, R, RE, PIR) | P4M à 15 m | CC BY 4.0 | [zenodo 22062459](https://zenodo.org/records/22062459) | oui (non testé ici) | 3 | 🔎 |
| WeedMap (ETH ASL 2018) | segmentation fond / culture / adventice (betterave) | 18 746 fichiers (~5,36 Go), 8 sous-jeux | masques par pixel | RedEdge-M (5) + Sequoia (4) | non vérifiée | **à confirmer** (l'article est CC BY 4.0) | [page](https://projects.asl.ethz.ch/datasets/weedmap-2018/) · doi:10.3929/ethz-c-000788571 | oui (non testé ici) | 3 | 🔎 |
| Kazakhstan, blé / soja / orge (*Data* 2023) | type de culture (aucune étiquette maladie) | non vérifié | type de culture | 5 + NDVI (P4M) | 3 cm | CC BY 4.0 | [zenodo 7860751](https://zenodo.org/records/7860751) | oui (non testé ici) | 3 | 🔎 |
| Blé de printemps, Brésil (Mendeley jzh4x3svv5) | biomasse par parcelle (aucune étiquette maladie) | non vérifié | mesures de biomasse | 4 (V, R, RE, PIR ; Sequoia) | 4,65 cm (vol à 50 m) | non vérifiée | [Mendeley](https://data.mendeley.com/datasets/jzh4x3svv5/2) | oui (non testé ici) | 3 | 🔎 |

## 5. Fiches : conditions de prise de vue et remarques

### 5.1 Pucerons et insectes

- **APHID-4K.** Pucerons du blé photographiés au champ (« in the wild »), en haute
  résolution ; le mode de prise de vue n'est pas vérifié. C'est
  le jeu le plus proche du besoin par l'espèce et la culture. Le détail par espèce lu dans
  un extrait ne correspond pas au total de 4 294 images, je ne le reporte donc pas.
  **Aucun lien de téléchargement trouvé** : il faut écrire aux auteurs en précisant l'usage
  commercial envisagé.
- **Pucerons du sorgho (Kansas).** Images de terrain prises à trois hauteurs de caméra
  (35 140, 13 311 et 6 291 patchs pour le haut, le milieu et le bas). Les annotations
  portent sur des **colonies** (seuil de 6 pucerons proches), pas sur des individus. Culture
  et espèce différentes (sorgho), mais c'est la seule base accessible qui ressemble à
  « repérer une infestation au champ depuis le haut ».
- **Pièges collants (Zenodo 7139220 et 14097660).** Pièges jaunes photographiés à 20 cm
  (7139220, en intérieur et en extérieur) ou au téléphone à 30–40 cm (14097660, serre de
  concombre, Volos, Grèce). Fond uniforme, insectes à plat, pucerons noirs alors que les
  pucerons des céréales sont souvent verts ou bruns. **Réponse à ta question : oui, au
  mieux du pré-entraînement « petits insectes ».** À garder seulement si une ablation
  montre un gain.
- **AphidCV.** Logiciel et images d'Embrapa Trigo et de l'Université de Passo Fundo
  (Brésil). D'après la description du logiciel, il traite l'image d'une plaque de verre
  portant les insectes, donc a priori en laboratoire (à confirmer sur les images). Les espèces sont exactement celles du blé (*Sitobion avenae*, *Rhopalosiphum
  padi*, *Metopolophium dirhodum*, *Schizaphis graminum*). Utile pour un **classifieur
  d'espèce ou de forme** en second étage, pas pour la détection au champ.
- **Coccinelles du blé.** Images en 640×640. Licence **CC BY-NC** selon un extrait (à
  confirmer) : exclu par prudence.
- **IP102.** Pas de fichier de licence dans le dépôt (vérifié). Selon l'article d'origine,
  non relu ici, les images viennent d'Internet. Exclu.
- **Roboflow Universe.** Nombreux petits jeux déposés par des utilisateurs. Leur licence
  CC BY 4.0 ne garantit pas les droits sur les images. Téléchargement avec un compte
  gratuit et une clé API. À évaluer au cas par cas, seulement si la provenance est
  documentée.
- **GreenFlyDB, AID-YOLO.** Introuvables malgré plusieurs formulations. Si tu as un DOI ou
  un lien, je les vérifie.

### 5.2 Maladies du blé

- **John Innes Centre (Norwich, Royaume-Uni).** Images de terrain et de serre, classées
  sain / rouille jaune / rouille brune / oïdium / septoriose, soit les maladies foliaires
  majeures du blé tendre en France. 999 images publiques (celles soumises à des
  pathologistes pour comparaison) ; jeu complet de 19 172 images sur demande.
- **WFD2020.** 2 414 images expertisées couvrant cinq maladies fongiques et
  le sain. Hébergé sur `wfd.sysbio.ru`. Licence à confirmer.
- **ETH Zurich 2026.** Feuilles suivies quasi quotidiennement au champ à Lindau-Eschikon
  (Suisse), saisons 2022–2023 et 2023–2024, à ~0,03 mm/px. Climat proche de la France,
  septoriose et rouilles. Très bon **jeu de test inter-sources**. La résolution est sans
  commune mesure avec celle d'un drone.
- **NWRD.** Images multi-feuilles au champ (NUST, Pakistan), masques de rouille jaune. Petit
  (100 images) mais annoté au pixel.
- **Éthiopie (Holeta).** Feuilles au champ, appareil reflex, conditions non contrôlées.
  Petit (407 images), mais CC BY 4.0 : candidat de test inter-sources.
- **GWHD 2021.** 6 515 images de couvert vu du dessus, 12 pays. Base de référence pour
  détecter les **épis**, avant toute classification au niveau de l'épi.
- **Écartés pour licence :** Yellow-Rust-19 (« Unknown »), StripeRust-Pocket (non
  commercial, vérifié dans l'accord). **Écartés pour disponibilité :** LWDCD2020.
  **Peu pertinents** (maladies ou contexte éloignés de la France) : Bangladesh, Inde.

### 5.3 Multispectral

- **Su et al. / Ir-UNet.** Caméra RedEdge à 5 bandes sur drone DJI, vol de 16 à 24 m
  (1–1,5 cm/px), champ de blé d'hiver **inoculé**, images du 23 mars au 7 mai 2018. C'est
  la cible idéale, mais **les données ne sont pas publiques**. Seule voie : une demande aux
  auteurs, en mentionnant l'usage commercial.
- **Agriculture-Vision.** Vérifié directement. Les conditions d'utilisation (PDF du bucket)
  n'accordent qu'une licence *« for the sole purpose of developing non-commercial research
  applications »* et interdisent de *« use the Dataset to develop, or otherwise in
  connection with, any commercial product or service »*. Même un pré-entraînement est donc
  exclu pour un produit commercial. Par ailleurs, les canaux sont normalisés en 8 bits par
  percentiles et ne sont pas de la réflectance calibrée.
- **Maïs, Turquie.** Drone P4M à 15 m, 5 bandes, sous licence CC BY 4.0. Mais les masques
  sont des **pseudo-étiquettes calculées à partir d'indices de végétation**. Comparer un
  U-Net à une baseline NDVI/NDRE sur ce jeu serait circulaire : le U-Net apprendrait les
  indices.
- **WeedMap.** Vraie vérité terrain par pixel avec un capteur RedEdge à 5 bandes, mais pour
  une autre tâche (adventices de la betterave). Licence du jeu à confirmer.
- **Kazakhstan, Brésil.** Images de blé en multispectral drone, sans étiquette de maladie
  ni de stress. Utiles seulement pour des statistiques de normalisation par bande ou un
  pré-entraînement auto-supervisé.

## 6. Vue drone : ce qui est réaliste pour les pucerons

Résolution au sol : `GSD = H × l / (f × N)`, avec H la hauteur au-dessus du couvert, l la
largeur du capteur, f la focale et N la largeur de l'image en pixels. Les deux capteurs
ci-dessous sont des exemples types, pas des modèles choisis.

| Capteur (exemple) | H | GSD | Puceron d'environ 2 mm |
|---|---|---|---|
| Plein format (l = 36 mm, N = 8192 px, f = 35 mm) | 2 m | 0,25 mm/px | ≈ 8 px |
| idem | 5 m | 0,63 mm/px | ≈ 3 px |
| idem | 10 m | 1,26 mm/px | ≈ 1,6 px |
| 4/3 (l = 17,3 mm, N = 5280 px, f = 12,3 mm) | 2 m | 0,53 mm/px | ≈ 4 px |
| idem | 5 m | 1,33 mm/px | ≈ 1,5 px |

La taille de ~2 mm est un ordre de grandeur pour un puceron des céréales adulte ; les
larves sont plus petites. En pratique, un détecteur a besoin d'une dizaine de pixels sur
l'objet pour être fiable. S'y ajoutent des contraintes qualitatives : le souffle des rotors
à 1–3 m agite le couvert (flou de bougé), et une partie des pucerons se trouve sous les
feuilles ou à la base des tiges.

**Conséquences proposées :**

1. Au niveau plante, viser les **colonies et les organes infestés** (épis colonisés en fin
   de printemps), à **2–3 m maximum**, avec un capteur haute définition stabilisé. Le
   comptage individuel ne se fait que dans les cas favorables.
2. Entre 10 et 30 m, on ne voit que des symptômes de couvert : c'est le rôle du niveau
   parcelle.
3. **Aucun jeu public ne remplacera un jeu drone propre** : il faut le collecter dès la
   saison prochaine. Les jeux publics servent au pré-entraînement et au développement de
   la chaîne.

Le même raisonnement vaut pour les maladies : les jeux publics sont des gros plans de
feuilles, très loin de la résolution d'un drone. L'écart de domaine sera mesuré au
chantier 4 en entraînant sur une source et en testant sur une autre.

## 7. Recommandation

### 7.1 Pucerons : détection (chantier 3)

| Rôle | Jeu | Condition |
|---|---|---|
| Entraînement « colonies » | Pucerons du sorgho (Dataverse) | licence confirmée CC0 ou CC BY |
| Entraînement « pucerons du blé » | APHID-4K | accord des auteurs, usage commercial compris |
| Pré-entraînement (ablation) | Pièges collants Zenodo 7139220 (CC BY 4.0), 14097660 si licence ouverte | garder seulement si gain mesuré |
| Second étage espèce / forme | AphidCV *Balanced 2k* (CC BY 4.0) | optionnel |
| Exclus | IP102, coccinelles (NC), Roboflow sans provenance, GreenFlyDB et AID-YOLO (introuvables) | — |

La baseline du chantier 3 validera la chaîne (petits objets, SAHI, métriques par taille
d'objet). **Elle ne mesurera pas la performance réelle en vue drone.**

### 7.2 Maladies : classification (chantier 4)

- **Classes proposées**, communes aux sources et pertinentes en France : sain, rouille
  jaune, rouille brune, septoriose, oïdium, plus une sortie « incertain ».
- **Entraînement :** John Innes (999 images, et le jeu complet si obtenu) + WFD2020 si sa
  licence est confirmée.
- **Test inter-sources :** ETH 2026 (Suisse) et feuilles d'Éthiopie. NWRD en option pour
  segmenter la rouille jaune.
- **Backbones :** EfficientNet-B0 et ConvNeXt-Tiny (timm), comme demandé. Option en plus :
  FoMo4Wheat ViT-B/14, pré-entraîné sur du blé et sous licence MIT.
- **Épis :** GWHD 2021 (CC BY 4.0) pour le détecteur d'épis. Aucun jeu ouvert et pertinent
  de maladies d'épi n'a été vérifié ; Dryad Guelph est à évaluer.
- **Exclus :** Yellow-Rust-19, StripeRust-Pocket, LWDCD2020.

### 7.3 Multispectral (chantier 5) : alternative proposée

Les données publiques ne permettent pas, en l'état, d'entraîner la tâche visée (zones
malades ou stressées du blé). Je propose :

1. **Construire la chaîne N bandes** (lecture GeoTIFF, normalisation par bande, tuilage,
   U-Net smp à N canaux) **et la baseline par indices** (NDVI, NDRE, Otsu).
2. **Valider cette chaîne techniquement sur WeedMap** (5 bandes RedEdge-M, vérité terrain
   manuelle), si sa licence est confirmée. C'est une autre tâche ; elle sert seulement à
   éprouver le code et la comparaison « deep learning contre indices » sur une vraie vérité
   terrain.
3. **Ne pas utiliser le jeu maïs** pour cette comparaison, à cause de ses pseudo-masques
   issus d'indices. Il peut servir de test de lecture des données.
4. **Demander les données** de Su et al. et de Nguyen et al. en mentionnant l'usage
   commercial.
5. **Préparer le protocole de collecte** du drone : panneau de calibration et réflectance,
   dates, notations au sol géolocalisées par parcelle. Ce jeu sera la vraie base du
   niveau parcelle.

## 8. Ce qu'il faut fournir ou décider

1. **Valider ou amender** les listes du §7.
2. **Réseau pour le chantier 2.** Deux options : autoriser les hôtes zenodo.org,
   data.mendeley.com, dataverse.harvard.edu, datadryad.org,
   www.research-collection.ethz.ch, figshare.com, wfd.sysbio.ru et huggingface.co dans les
   réglages réseau de l'environnement cloud ; ou lancer les scripts de téléchargement sur
   ta machine.
3. **Clés et comptes.** Aucun n'est nécessaire pour la liste recommandée : Zenodo,
   Mendeley, Dataverse, Figshare et ETH sont publics. Seulement si tu le souhaites :
   - Roboflow : compte gratuit et clé API, à fournir dans la variable d'environnement
     `ROBOFLOW_API_KEY` ;
   - Kaggle : fichier `kaggle.json` ou variables `KAGGLE_USERNAME` et `KAGGLE_KEY` (aucun
     jeu Kaggle n'est retenu) ;
   - Zindi : compte et acceptation du règlement, pour évaluer le jeu CGIAR.
4. **Demandes aux auteurs**, que je peux rédiger : APHID-4K (Du et al.), jeu complet John
   Innes (Long, Brown et al.), données RedEdge de Su et al., données P4M de Nguyen et al.
5. **GreenFlyDB et AID-YOLO** : un lien ou un DOI si tu en as.
6. **Arbitrages :** (a) recentrer la détection de pucerons sur les colonies et épis
   infestés, à très basse altitude ; (b) adopter le chantier 5 alternatif (§7.3).

## 9. Sources principales

- Agriculture-Vision : [bucket S3](https://intelinair-data-releases.s3.amazonaws.com/?prefix=agriculture-vision/&delimiter=/)
  (conditions d'utilisation et article lus), [arXiv:2001.01306](https://arxiv.org/abs/2001.01306).
- Pucerons : [Zenodo 7139220](https://zenodo.org/records/7139220),
  [Zenodo 14097660](https://zenodo.org/records/14097660),
  [APHID-4K (Neurocomputing 2022)](https://www.sciencedirect.com/science/article/abs/pii/S0925231221018506),
  [TD-Det (Insects 2022)](https://doi.org/10.3390/insects13060501),
  [Sorgho (J. Imaging 2024)](https://doi.org/10.3390/jimaging10050114),
  [AphidCV FULL](https://zenodo.org/records/20145802), [AphidCV Balanced 2k](https://zenodo.org/records/20138274),
  [Coccinelles (Data in Brief 2024)](https://www.sciencedirect.com/science/article/pii/S2352340924005523),
  [IP102](https://github.com/xpwu95/IP102),
  [Aphid-YOLO](https://eprints.whiterose.ac.uk/id/eprint/230321/).
- Maladies : [WFD2020 (Plants 2021)](https://doi.org/10.3390/plants10081500),
  [John Innes (Plant Pathology 2023)](https://doi.org/10.1111/ppa.13684),
  [ETH 2026 (Scientific Data)](https://www.nature.com/articles/s41597-026-06567-y),
  [NWRD](https://github.com/dll-ncai/NUST-Wheat-Rust-Disease-NWRD),
  [StripeRust-Pocket](https://github.com/WeizhenLiuBioinform/StripeRustNet),
  [GWHD 2021](https://doi.org/10.5281/zenodo.5092309),
  [FoMo4Wheat](https://github.com/PheniX-Lab/FoMo4Wheat).
- Multispectral : [Su et al. 2018](https://www.sciencedirect.com/science/article/pii/S0168169918312584),
  [Ir-UNet](https://doi.org/10.3390/rs13193892), [Nguyen et al. 2023](https://doi.org/10.3390/rs15133301),
  [revue des jeux MS drone (Remote Sens. 2026)](https://doi.org/10.3390/rs18040659)
  (39 jeux recensés, à exploiter si l'accès réseau est ouvert),
  [WeedMap](https://projects.asl.ethz.ch/datasets/weedmap-2018/),
  [maïs, Turquie](https://zenodo.org/records/22062459),
  [Kazakhstan](https://doi.org/10.3390/data8050088).
