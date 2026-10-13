# TP : reconnaître les maladies et les parasites de l'olivier

Deux travaux pratiques pour construire, pas à pas, les deux briques « niveau plante »
du drone, sur des données publiques réelles :

| TP | Question | Type de modèle | Données | Durée indicative |
|---|---|---|---|---|
| [TP 1](tp1_maladies_feuilles.ipynb) | Cette feuille est-elle saine, atteinte d'œil de paon ou d'acariose (acarien *Aculus olearius*) ? | classification d'images (EfficientNet-B0, PyTorch + timm) | Uğuz et Uysal (Turquie) ; tests : Diker (Turquie, autre équipe), Pérou | 3 à 4 h |
| [TP 2](tp2_parasites_pieges.ipynb) | Combien de mouches de l'olive (femelles, mâles) dans ce piège ? | détection d'objets (YOLO11n, Ultralytics) | SmartMcPhail ; tests : DIRT (Grèce), piège numérique de Leucade | 3 à 4 h |

Chaque notebook contient des explications, des cellules **À FAIRE** à compléter et des
questions ❓ pour le compte rendu. Les corrigés complets sont dans
[`corriges/`](corriges/) : ne les ouvrez qu'après avoir essayé.

## Ce que vous saurez faire à la fin

- explorer un jeu d'images et y repérer les pièges : doublons, fuites entre
  entraînement et test, fonds trop uniformes, classes déséquilibrées ;
- découper un jeu de données sans fuite (groupes de quasi-doublons) ;
- poser une référence simple avant le deep learning ;
- entraîner un réseau pré-entraîné (classification) et un détecteur (YOLO) ;
- évaluer comme il faut :
  - rappel par classe et matrice de confusion ;
  - seuil « incertain » réglé sur la validation ;
  - mAP de détection ;
  - erreur de comptage ;
  - et surtout **test sur des images d'une autre source** ;
- voir où regarde un réseau (Grad-CAM), sauvegarder un modèle et l'utiliser sur une
  nouvelle image.

## Installation (une fois)

1. Suivez les **étapes 1 et 2** de la section « Télécharger toutes les données sur votre
   PC » du [README du projet](../README.md) : installer Git, uv et un outil RAR, puis
   récupérer le projet. **Ne lancez pas l'étape 3** : sans argument, `data download`
   télécharge tous les jeux du projet (plus de 170 Go). Pour les TP, six jeux suffisent.
2. Depuis la racine du projet :

   ```bash
   uv sync --group notebooks          # dépendances + JupyterLab
   uv run agridrone data download olive_leaf_uguz_uysal olive_leaf_peacock_diker olive_leaf_peacock_peru
   uv run agridrone data download olive_fly_smartmcphail olive_fly_dirt_coco olive_fly_digital_mcphail
   uv run jupyter lab tp/
   ```

3. **Avant de commencer**, enregistrez chaque notebook sous un autre nom (Fichier >
   Enregistrer sous…, par exemple `tp1_maladies_feuilles_NOM.ipynb`) : un `git pull` ou
   une régénération des notebooks écraserait les fichiers d'origine.

Prévoyez environ 10 Go de disque : 3,5 Go de données (archives et extractions) et 2 à
7 Go pour l'environnement Python (PyTorch). Les poids pré-entraînés (EfficientNet-B0,
YOLO11n) se téléchargent automatiquement à la première exécution.

**Matériel.** Un GPU NVIDIA rend le travail confortable, mais tout fonctionne sans :
les notebooks détectent le matériel et passent en **mode rapide** (moins d'époques,
images plus petites). Les résultats sont alors un peu moins bons, mais toutes les étapes
sont faisables. Durées mesurées sur un CPU 4 cœurs : environ 15 minutes d'entraînement
pour le TP 1, 30 minutes pour le TP 2.

- **Windows + carte NVIDIA** : `uv sync` installe un PyTorch sans CUDA, et les
  notebooks afficheront « Matériel : cpu ». Pour utiliser la carte, suivez « PyTorch et
  GPU » dans le README du projet, puis vérifiez avec `uv run agridrone info`.
- **Mac Apple Silicon** : les notebooks utilisent le GPU du Mac (`mps`), en mode rapide.
- **Windows et macOS** : les images sont chargées dans le processus principal
  (`NUM_WORKERS = 0`). C'est plus lent, mais cela évite une erreur de multiprocessing
  dans les notebooks.

## Déroulé conseillé

1. **TP 1, parties 1 et 2** (données, doublons, découpage) : c'est là que se jouent la
   plupart des erreurs en apprentissage automatique. Ne les survolez pas.
2. **TP 1, parties 3 à 5** : référence, entraînement, évaluation, seuil « incertain ».
3. **TP 1, parties 6 à 8** : test hors source, Grad-CAM, sauvegarde.
4. **TP 2** en entier.
5. Le compte rendu (voir la fin de chaque notebook).

## Résultats de référence

Mesurés le 13 octobre 2026 en exécutant les corrigés sur un CPU 4 cœurs (Xeon, sans
GPU), donc en **mode rapide**. Le mode complet sur GPU n'a pas été mesuré ici.

**TP 1** (192 px, 8 époques d'environ 105 s ; 16 minutes pour tout le notebook)

| Étape | Résultat |
|---|---|
| Doublons | 94 copies en trop ; 24 photos (MD5) communes au train et au test officiels |
| Quasi-doublons (dHash 256 bits, seuil 3) | 106 groupes à cheval sur train et test ; le test passe de 680 à 574 images |
| Référence (histogrammes + régression logistique) | exactitude de validation 0,71 |
| EfficientNet-B0 | validation 0,94 ; test 0,92 (rappel : sain 0,87, œil de paon 0,92, acariose 0,94) |
| Seuil « incertain » (98 % visé sur la validation) | seuil 0,78 : 70 % du test décidé, à 98,5 % d'exactitude |
| Pérou (hors source) | sain / malade 0,98 ; rappel des malades 0,97 ; fausses alertes 1,3 % ; 83 % décidé |
| Turquie, Diker (hors source) | sain / malade 0,91 ; rappel des malades 0,95 ; fausses alertes 12 % ; 41 % décidé |

**TP 2** (640 px, 60 époques d'environ 28 s ; 29 minutes pour tout le notebook)

| Étape | Résultat |
|---|---|
| Taille des insectes | largeur médiane 13 px à 640 px (10e centile 7 px), 20 px à 1024 px |
| Test, 3 classes | mAP50 0,51 ; mAP50-95 0,33 (femelle 0,43, mâle 0,47, pyrale 0,64 sur 7 objets) |
| Test, une seule classe « insecte » | mAP50 0,80 (précision 0,78, rappel 0,77) |
| Comptage | `CONF` = 0,25 choisi sur la validation ; test : 2,3 mouches d'erreur par image, 255 prédites pour 261 |
| DIRT (hors source, une classe) | mAP50 0,09 (précision 0,14, rappel 0,16) |
| Leucade (hors source, comptage expert) | erreur de 36 mouches par image ; 937 comptées pour 5 390, l'écart croissant avec le remplissage du piège |

Ces chiffres servent de repère, pas de cible à atteindre au point près. Un écart de
quelques points vient de la graine, du matériel ou du mode. La leçon principale est
dans les deux dernières lignes de chaque tableau : un modèle bon sur sa source peut
s'effondrer ailleurs.

## Grille d'auto-évaluation

| Compétence | Je sais… |
|---|---|
| Données | compter, visualiser, trouver doublons exacts et quasi-doublons |
| Découpage | expliquer et éviter une fuite train → test |
| Référence | justifier l'intérêt d'un modèle simple avant le deep learning |
| Entraînement | écrire une boucle PyTorch (passe avant, perte, rétropropagation, pas d'optimisation) |
| Évaluation | lire une matrice de confusion, choisir un seuil sur la validation (jamais sur le test) |
| Généralisation | mesurer et expliquer la chute sur une autre source |
| Interprétation | produire et commenter une carte Grad-CAM, repérer un raccourci (fond, bords) |
| Réutilisation | sauvegarder un modèle avec ses réglages (classes, taille, seuil) et diagnostiquer une nouvelle image |
| Détection | convertir COCO vers YOLO, lire IoU, précision, rappel et mAP |
| Comptage | passer des boîtes à la mesure utile (mouches par piège) et en mesurer l'erreur |

## Questions fréquentes

- **`FileNotFoundError` sur `data/interim/...`** : le jeu n'est pas téléchargé, ou
  l'extraction RAR a échoué (installez 7-Zip, unar ou unrar, puis relancez la commande
  `data download`). Autre cause : les données sont ailleurs. Si vous avez utilisé
  `configs/local.yaml`, remplacez dans la cellule 0 `DATA = ROOT / "data" / "interim"`
  par votre chemin, par exemple `DATA = Path("D:/agridrone/interim")`.
- **`ModuleNotFoundError: No module named 'timm'` (ou `ultralytics`)** : Jupyter
  n'utilise pas l'environnement du projet. Lancez-le avec `uv run jupyter lab tp/`
  depuis la racine du projet (pas depuis Anaconda). Sous VS Code, choisissez
  l'interpréteur `.venv`.
- **`jupyter` introuvable après un `uv sync`** : relancez `uv sync --group notebooks`.
- **Windows : `OSError: [WinError 126]` à l'import de torch** : installez le
  « Microsoft Visual C++ Redistributable » (x64), puis redémarrez.
- **`CUDA out of memory`** : baissez `BATCH` (TP 1), ou `BATCH` puis `IMGSZ` (TP 2).
- **Le noyau redémarre (mémoire)** : fermez les autres notebooks et applications, puis
  baissez `BATCH` (16, puis 8). Ce sont les entraînements (TP 1, partie 4 ; TP 2,
  partie 3) qui demandent le plus de mémoire vive.
- **Résultats différents à chaque exécution** : le GPU n'est pas déterministe. Les
  écarts doivent rester faibles.
- **(Enseignants) Modifier les énoncés** : éditez `build_notebooks.py`, puis lancez
  `uv run python tp/build_notebooks.py`, qui réécrit `tp/*.ipynb` et
  `tp/corriges/*.ipynb`.

## Licences des données

Usage académique, non commercial. Les jeux d'Uğuz et Uysal et de Diker n'ont pas de
licence publiée, et celui du Pérou est sous CC BY-NC-SA 4.0. Citez les auteurs
(références dans [`LICENCES_DONNEES.txt`](../LICENCES_DONNEES.txt)).
