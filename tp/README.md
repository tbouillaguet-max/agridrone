# TP : reconnaître les maladies et les parasites de l'olivier

Deux travaux pratiques pour construire, pas à pas, les deux briques « niveau plante »
du drone, sur des données publiques réelles :

| TP | Question | Type de modèle | Données | Durée indicative |
|---|---|---|---|---|
| [TP 1](tp1_maladies_feuilles.ipynb) | Cette feuille est-elle saine, atteinte d'œil de paon ou d'acariose (acarien *Aculus olearius*) ? | classification d'images (EfficientNet-B0, PyTorch + timm) | Uğuz et Uysal (Turquie) ; tests : Diker (Turquie), Pérou | 3 à 4 h |
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
  - seuil « incertain » ;
  - mAP de détection ;
  - erreur de comptage ;
  - et surtout **test sur des images d'une autre source** ;
- voir où regarde un réseau (Grad-CAM), sauvegarder un modèle et l'utiliser sur une
  nouvelle image.

## Installation (une fois)

Suivez d'abord la section « Télécharger toutes les données sur votre PC » du
[README du projet](../README.md) (Git, uv, outil RAR). Puis, depuis la racine du projet :

```bash
uv sync --group notebooks          # dépendances + JupyterLab
uv run agridrone data download olive_leaf_uguz_uysal olive_leaf_peacock_diker olive_leaf_peacock_peru
uv run agridrone data download olive_fly_smartmcphail olive_fly_dirt_coco olive_fly_digital_mcphail
uv run jupyter lab tp/
```

Il faut environ 2 Go de téléchargement et 4 Go de disque avec les extractions. Les poids
pré-entraînés (EfficientNet-B0, YOLO11n) se téléchargent automatiquement à la première
exécution.

**Matériel.** Un GPU NVIDIA rend le travail confortable, mais tout fonctionne sur CPU :
les notebooks détectent le matériel et passent en **mode rapide** (moins d'époques,
images plus petites). Les résultats sont alors un peu moins bons, mais toutes les étapes
sont faisables. Sur Windows et macOS, les images sont chargées dans le processus
principal (`NUM_WORKERS = 0`), ce qui est plus lent mais évite une erreur de
multiprocessing dans les notebooks.

## Déroulé conseillé

1. **TP 1, parties 1 et 2** (données, doublons, découpage) : c'est là que se jouent la
   plupart des erreurs en apprentissage automatique. Ne les survolez pas.
2. **TP 1, parties 3 à 5** : référence, entraînement, évaluation, seuil « incertain ».
3. **TP 1, parties 6 à 8** : test hors source, Grad-CAM, sauvegarde.
4. **TP 2** en entier.
5. Le compte rendu (voir la fin de chaque notebook).

## Résultats de référence

Obtenus en exécutant les corrigés sur le CPU de développement (4 cœurs, sans GPU), donc
en **mode rapide**. Sur GPU (mode complet), attendez-vous à mieux.

<!-- RESULTATS -->

Ces chiffres servent à vous situer, pas de cible à atteindre au point près. Un écart de
quelques points vient de la graine, du matériel ou du mode.

## Grille d'auto-évaluation

| Compétence | Je sais… |
|---|---|
| Données | compter, visualiser, trouver doublons exacts et quasi-doublons |
| Découpage | expliquer et éviter une fuite train → test |
| Référence | justifier l'intérêt d'un modèle simple avant le deep learning |
| Entraînement | écrire une boucle PyTorch (passe avant, perte, rétropropagation, pas d'optimisation) |
| Évaluation | lire une matrice de confusion, choisir un seuil « incertain » sur la validation |
| Généralisation | mesurer et expliquer la chute sur une autre source |
| Détection | convertir COCO vers YOLO, lire précision, rappel et mAP |
| Comptage | passer des boîtes à la mesure utile (mouches par piège) et en mesurer l'erreur |

## Questions fréquentes

- **`FileNotFoundError` sur `data/interim/...`** : le jeu n'est pas téléchargé, ou
  l'extraction RAR a échoué (installer 7-Zip, unar ou unrar, puis relancer la commande
  `data download`).
- **`CUDA out of memory`** : baisser `BATCH` (TP 1) ou `BATCH`, puis `IMGSZ` (TP 2).
- **Le kernel redémarre (mémoire)** : fermer les autres notebooks ; en TP 1, la
  matrice des distances de 3 400 × 3 400 empreintes demande environ 100 Mo.
- **Résultats différents à chaque exécution** : le GPU n'est pas déterministe. Les
  écarts doivent rester faibles.
- **Modifier les notebooks** : ils sont générés par `build_notebooks.py`, à éditer puis
  relancer (`uv run python tp/build_notebooks.py`). Vos copies de travail peuvent être
  modifiées librement : enregistrez-les sous un autre nom.

## Licences des données

Usage académique, non commercial. Le jeu d'Uğuz et Uysal n'a pas de licence publiée, et
celui du Pérou est sous CC BY-NC-SA 4.0. Citez les auteurs (références dans
[`LICENCES_DONNEES.txt`](../LICENCES_DONNEES.txt)).
