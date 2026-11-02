# Livrable 1 — Inventaire vérifié, recommandation et choix de l'approche

Date de vérification : 21 octobre 2026. Les informations viennent des fiches publiques des jeux de données. Aucun téléchargement n'a été testé (le réseau de l'environnement local est bloqué) : les tests d'accès sont faits au livrable 2. Un « ? » signifie « non vérifié ».

## 1. État de l'art rapide (limité aux sources consultées)

- Photos de feuilles en laboratoire (PlantVillage) : très répandues, mais l'article Cornell rapporte que des CNN entraînés sur ce type de jeux ont mal fonctionné sur des images de champ. PlantDoc (images prises sur le web, CC BY 4.0) a été créé pour répondre à ce problème.
- Photos de champ au smartphone avec boîtes (KaraAgro, Makerere, MLD) : gros volumes, classes ravageurs et striure.
- Drone : seulement Cornell (helminthosporiose) et IIITDMJ (416 images). Aucun jeu drone public vérifié ne couvre à la fois sain, maladies et ravageurs.
- Détecteurs : YOLO (Ultralytics) est léger et rapide. RT-DETR (transformer) n'a de poids préentraînés qu'en tailles L et X.

## 2. Tableau comparatif

| Source | Prise de vue | Résolution | Images | Classes | Annotations | Licence | Accès | Statut |
|---|---|---|---|---|---|---|---|---|
| Cornell NLB drone | Drone DJI Matrice 600, 6 m, nadir, 1 m/s, 1 image / 2 s | 6000×4000 (moy.) | 7 669 (≈50 Go) | Helminthosporiose (NLB) seule | 42 117 lésions, lignes/splines (pas de boîtes) | CC0 selon l'article des auteurs (à reconfirmer sur OSF) | Zip sur CNCB/OPIA, dépôt OSF | Retenu (échantillon) |
| KaraAgro AI Maize (Ghana) | Plein champ (appareil ? non précisé) | jusqu'à 4608 px | 16 552 | Striure, dégâts/larves/œufs/déjections de légionnaire d'automne, sain | 92 934 boîtes | CC0 | Harvard Dataverse, doi 10.7910/DVN/CXUMDS (31 Go en format Supervisely) | Retenu (principal) |
| Makerere (Ouganda) | Smartphone, jardins de fermiers | 1024×1024 à 2000×3200 | 15 821 | Sain (5 326), helminthosporiose (5 279), striure (5 216) | Boîtes ≈ image entière (1 objet/image, ~94 % de la surface) | CC0 | Harvard Dataverse, doi 10.7910/DVN/LPGHKK (12 Go) | Retenu |
| MLD Bangladesh | Smartphone (iPhone 13, S21), soleil naturel | 640×480 (redimensionné) | 1 996 | Helminthosporiose 489, légionnaire 525, cercosporiose 555, sain 427 | Format ? (classes) | CC BY 4.0 | Mendeley, doi 10.17632/3myfctrgk3.1 | Retenu |
| PlantDoc | Images web, fonds variés | variable | ≈2 500–2 600 (13 espèces) | Maïs : helminthosporiose (186 im.), rouille (112), cercosporiose | Boîtes | CC BY 4.0 | GitHub, Roboflow | Retenu (petit appoint) |
| IIITDMJ_Maize | Drone (images extraites de vidéo) | 224×224 | 416 + 50/classe en test | Rouille, helminthosporiose, cercosporiose, sain | Étiquettes d'image | ? | Abonnement IEEE DataPort requis | Exclu (école sans abonnement) |
| PlantVillage (maïs) | Feuilles en laboratoire | 256×256 | 3 852 | 4 classes dont sain | Étiquettes d'image | ? | GitHub | Exclu du test |
| FAW thermique + RGB | FLIR E8 + iPhone | ? | ? (38 augmentations) | Sain / infesté | ? | ? | Figshare | À examiner plus tard |
| Corn Leaf Diseases (YOLO, 4 027 im.) | ? | ? | 4 027 | Rouille, cercosporiose, helminthosporiose, sain | Boîtes | « Other » | Kaggle | Exclu (origine non vérifiée) |

Candidat non vérifié : jeu Mendeley sb4wwjs8bz (Bangladesh, 10 classes de maladies, juin 2026), à examiner au livrable 2 (licence et effectifs inconnus).

## 3. Constats qui orientent le projet

1. **Aucune source publique ne donne des images de drone saines, malades et avec ravageurs.** La priorité 1 de ton cahier des charges n'est pas couverte par des données publiques : tes propres images de drone seront indispensables.
2. **Makerere : les boîtes englobent presque toute l'image.** Ce sont en pratique des étiquettes d'image, pas de la localisation.
3. **KaraAgro : de vraies boîtes pour les dégâts de légionnaire** (38 076 objets, environ 3 % de la surface de l'image en moyenne). Les noms de fichiers ressemblent à des exports Roboflow : des doublons ou images augmentées sont probables (inférence, à confirmer). Dédoublonnage obligatoire avant tout découpage.
4. **Cornell : annotations en lignes, essais inoculés, annotation probablement partielle** (le champ large rend l'annotation complète difficile). Les tuiles sans lésion annotée sont donc des négatifs bruités. De plus, une image toutes les 2 s à 1 m/s avec un grand champ implique de forts chevauchements : le découpage doit se faire par vol ou par bloc, jamais au hasard.

## 4. Combinaison recommandée et harmonisation des classes

- **Entraînement (domaine champ)** : KaraAgro + Makerere + MLD + PlantDoc.
- **Domaine drone** : tuiles Cornell (positifs NLB, en échantillon) pour l'évaluation « drone ». IIITDMJ est exclu : l'école n'a pas d'abonnement IEEE DataPort.
- **PlantVillage** : exclu du test et de la validation ; éventuellement utilisé en préentraînement seulement.

Harmonisation vers SAIN / MALADE_OU_RAVAGEUR, avec la classe d'origine conservée en métadonnée pour le futur multi-classe : sain → SAIN ; striure, helminthosporiose, rouille, cercosporiose, légionnaire (dégâts, larve, œuf, déjections) → MALADE_OU_RAVAGEUR. Les classes ambiguës de KaraAgro (« none healthy », « healthy images ») sont inspectées à la main avant d'être affectées.

## 5. Écart de domaine (gros plan contre drone)

- **Échelle** : en gros plan, la feuille remplit l'image ; en drone, une lésion fait quelques dizaines de pixels.
- **Fond et angle** : sol, ombres, rangs, plusieurs plants ; vue du dessus.
- **Raccourci d'apprentissage** : si le « sain » et le « malade » viennent de sources différentes, le modèle apprend la source (appareil, lumière).

Parades prévues : (1) réduire les images de gros plan pour que les symptômes aient une taille en pixels comparable à celle du drone (voir §7) ; (2) équilibrer sain et malade au sein de chaque source ; (3) évaluer séparément par source (champ contre drone) ; (4) collecter tes propres images de drone tôt (livrable 7), avec un petit jeu d'étalonnage de quelques centaines de tuiles annotées par classe (ordre de grandeur de ma part, non vérifié).

## 6. Choix de l'approche

**Décision : classification de tuiles comme base de la v1 ; YOLO en détection comme comparaison.**

- Les boîtes réellement exploitables sont celles de KaraAgro (domaine smartphone) et des boîtes approximées à partir des lignes de Cornell. Il n'y en a aucune en domaine drone, et les annotations de Cornell sont partielles, alors que la documentation Ultralytics précise qu'un étiquetage partiel ne fonctionne pas.
- **Seuil pour basculer vers la détection** : Ultralytics recommande au moins 1 500 images et 10 000 instances étiquetées par classe. Dans le domaine champ, KaraAgro dépasse ce seuil pour plusieurs classes (dégâts de légionnaire : 5 138 images, 38 076 objets ; déjections : 15 218 objets ; striure : 13 607 ; sain : 22 707). Les larves (1 512 objets) et les œufs (1 026) sont en dessous. En domaine drone, on en est à zéro : la détection devient pertinente une fois tes images de drone annotées atteignant ce seuil (≥1 500 images et ≥10 000 boîtes pour la classe MALADE_OU_RAVAGEUR). Avec un préentraînement sur le domaine smartphone, un volume plus faible pourrait suffire (hypothèse à tester, non vérifiée).

Modèles comparés (mêmes données, mêmes découpages, mêmes métriques) :
1. YOLO (Ultralytics), taille nano ou small : détection sur les boîtes disponibles, et mode classification sur tuiles.
2. EfficientNet-B0 et MobileNetV3 en classification de tuiles (référence).
3. RT-DETR : uniquement les tailles L et X ont des poids préentraînés. L'export ONNX est possible mais la documentation insiste sur les accélérateurs GPU : comparaison côté GPU, avec mesure du temps sur CPU au livrable 5.
4. **Ajout proposé** : caractéristiques d'un modèle de fondation gelé (par exemple DINOv2 petit) avec une tête linéaire. C'est robuste quand les données annotées du domaine cible sont rares, mais plus lourd que MobileNetV3 sur CPU. Je ne l'entraînerai que si le temps le permet, et je vérifierai sa licence avant.

## 7. Altitude, résolution au sol et taille de tuile

Formule : GSD (cm/pixel) = altitude (m) × largeur du capteur (mm) × 100 / (focale (mm) × largeur de l'image en pixels).

Hypothèse sur les lésions : l'helminthosporiose donne des lésions de 1 à 6 pouces (≈ 2,5 à 15 cm) selon Cornell Extension. Je retiens comme règle pratique (heuristique de ma part) qu'un symptôme doit faire au moins 10 pixels de large.

| Caméra | Altitude | GSD | Largeur au sol | Lésion 2,5–15 cm | Tuile 512 px |
|---|---|---|---|---|---|
| 1/2,3″, 12 MP (6,17 mm ; f 3,61 mm ; 4000 px) | 5 m | 0,21 cm/px | 8,5 m | 12–70 px | 1,09 m |
| idem | 6 m | 0,26 cm/px | 10,3 m | 10–59 px | 1,31 m |
| idem | 10 m | 0,43 cm/px | 17,1 m | 6–35 px | 2,19 m |
| 1″, 20 MP (13,2 mm ; f 8,8 mm ; 5472 px) | 8 m | 0,22 cm/px | 12,0 m | 11–68 px | 1,12 m |
| idem | 10 m | 0,27 cm/px | 15,0 m | 9–55 px | 1,40 m |

**Recommandation** : voler à environ 5–6 m avec un capteur 1/2,3″ (ou jusqu'à 8–10 m avec un capteur 1″) pour rester autour de 0,2–0,25 cm/pixel. Tuiles de 512×512 pixels (≈1,1–1,3 m au sol), redimensionnées à 256 ou 384 pour les classifieurs et utilisées à 640 pour YOLO. Plus bas, on gagne en détail mais on multiplie les photos et le temps de vol. À confirmer avec ta vraie caméra (question 1 : défaut appliqué).

## 8. Kaggle (limites vérifiées)

- GPU gratuit : 30 h par semaine en moyenne (un comparatif note que le quota réel varie, avec des estimations entre 15 et 30 h), sessions GPU jusqu'à 12 h, GPU T4 (×2) ou P100, stockage persistant ≈20 Go.
- Vérification du téléphone requise pour le GPU ; l'accès Internet des notebooks peut aussi l'exiger.
- **Conséquences pour le livrable 2** : sauvegarde d'un checkpoint à chaque époque, sessions de 3 à 4 h maximum, budget visé ≤ 15 h GPU par semaine. KaraAgro pèse 31 Go dans son format Supervisely, soit plus que les 20 Go de stockage : le notebook devra télécharger le format d'origine (taille non vérifiée, la page Dataverse n'a pas pu être lue), redimensionner et ne garder que le sous-ensemble utile.

## 9. Licences des outils

- **Ultralytics (YOLO)** : AGPL-3.0, ou licence Enterprise payante pour un usage commercial. Les modèles entraînés sont aussi sous AGPL-3.0 par défaut. Sans problème pour un travail académique ; à signaler si le projet devient commercial ou est distribué dans une application fermée.
- **RT-DETR via Ultralytics** : la page de documentation ne précise pas la licence. Comme l'implémentation est dans le même paquet, je considère qu'elle suit l'AGPL-3.0 (inférence, à confirmer).
- **EfficientNet-B0, MobileNetV3, ONNX Runtime, DINOv2** : licences non vérifiées dans cette étape. Elles sont généralement permissives, mais je les confirmerai dans les dépôts avant le livrable où elles servent.
- **Données** : CC0 (KaraAgro, Makerere), CC BY 4.0 (MLD, PlantDoc : attribution obligatoire). Cornell : CC0 d'après la section « Availability of data » de l'article (BMC Research Notes, 2018), à reconfirmer sur la page OSF. IIITDMJ, PlantVillage : licence non trouvée.

## 10. Fichiers fournis, à vérifier, suite

- Fichiers : `LIVRABLE_1_inventaire.md` (ce document) et `SOURCES.csv` (mis à jour).
- À vérifier de ton côté : (1) la licence de Cornell sur la page OSF du jeu (https://osf.io/p67rz/), que je n'ai pas pu lire (l'article des auteurs indique CC0) ; (2) les pages Dataverse de KaraAgro et Makerere, que mon outil n'a pas pu ouvrir (licence CC0 vue sur Dataset Ninja) ; (3) si ton école a un abonnement IEEE DataPort ; (4) que ton compte Kaggle est vérifié par téléphone.
- Livrable suivant : **2 — Notebook Kaggle de préparation des données.**
