# Livrable 3 — Entraînement et comparaison des modèles

Notebook : `notebooks/02_entrainement_comparaison.ipynb` (source lisible : `.py`, même contenu).
Entrée : la sortie du notebook 01 en mode « complet » (`maize_prep/`). Sortie : `/kaggle/working/train/`.

## Modèles comparés

| Nom | Modèle | Tâche | Entrée | Rôle dans la comparaison |
|---|---|---|---|---|
| `effnet_b0` | EfficientNet-B0 (timm, ImageNet) | classification de tuile | 512 px | référence légère |
| `mnv3_large` | MobileNetV3-Large (timm, ImageNet) | classification de tuile | 512 px | le plus rapide sur CPU |
| `yolo26n_cls` | YOLO26 nano-cls (Ultralytics, ImageNet) | classification de tuile | 512 px | YOLO imposé, version classification |
| `yolo26n_det` | YOLO26 nano (Ultralytics, COCO) | détection, 1 classe | 512 px | YOLO imposé : localise les lésions |
| `yolo26s_det` | YOLO26 small (Ultralytics, COCO) | détection, 1 classe | 512 px | YOLO imposé, plus grand |
| `dinov2s_lin` | DINOv2-small gelé + régression logistique | classification de tuile | 448 px | auto-supervisé, plus robuste au changement de domaine |
| `rtdetr_l` | RT-DETR-L (désactivé par défaut) | détection | 512 px | demandé « si les boîtes le permettent » ; pas de version légère pré-entraînée, trop lent sur CPU |

YOLO26 est la génération actuelle d'Ultralytics (version 8.4.183 utilisée) ; elle est conçue sans NMS, ce qui
simplifie l'export ONNX du livrable 5. Pour revenir à YOLO11, remplacer `yolo26n.pt` par `yolo11n.pt`.

## Protocole (identique pour tous les modèles)

1. **Mêmes ensembles** train / val / test, issus du découpage par groupes du notebook 01 (aucune fuite).
   Un contrôle anti-fuite est refait au chargement.
2. **Augmentations** adaptées à la vue de dessus : retournements horizontal et vertical, rotations de 90°,
   variations de couleur et d'éclairage, léger flou (bougé, mise au point), et une réduction-agrandissement
   aléatoire qui simule un drone plus haut (résolution au sol plus grossière).
3. **Déséquilibre des classes** : poids de classe inverses à la fréquence (classifieurs timm),
   `class_weight="balanced"` (DINOv2).
4. **Score par image** : probabilité « malade » pour les classifieurs ; pour la détection, confiance de la boîte la
   plus sûre (0 si aucune). Tous les modèles sont ainsi jugés sur la même question : « cette tuile est-elle
   malade ? », sur le même jeu de test (y compris les images sans boîtes).
5. **Seuil** : choisi sur la validation, c'est le plus grand seuil qui garde un rappel MALADE ≥ 95 %
   (`RECALL_TARGET`). Il est appliqué tel quel au test.
6. **Choix du modèle, sur la validation seulement** : meilleure précision au rappel cible ; à 0,01 près, on prend le
   plus rapide sur CPU. Le test sert uniquement à rapporter le résultat.
7. **Incertitude** : intervalles à 95 % du rappel et de la précision par bootstrap sur les groupes d'images
   (les images d'un même groupe sont corrélées : un bootstrap image par image serait trop optimiste).
8. **Détail** : rappel, précision et spécificité par source et par maladie (étiquette fine), au même seuil.

## Points de reprise et budget de temps

- Classifieurs timm : `last.pt` (modèle, optimiseur, planificateur, époque) à chaque époque, `best.pt` sur la
  meilleure AP de validation, arrêt anticipé après 6 époques sans progrès.
- YOLO : points de reprise Ultralytics (`weights/last.pt`) ; reprise avec `resume=True`.
- Budget : `max_hours` par modèle et `SESSION_HOURS = 11` pour toute la session. Un modèle coupé par le budget
  n'est pas marqué terminé et reprend à la session suivante. Les modèles terminés sont sautés.
- Reprise inter-sessions : ajouter la sortie de la version précédente de ce notebook en Input, puis relancer.

Estimation sur un GPU T4 avec environ 20 000 tuiles : environ 1 à 1,5 h par classifieur, 1,5 à 2,5 h par YOLO de
détection, moins de 30 min pour DINOv2. Il faut donc compter environ 9 h de GPU en tout, en une ou deux sessions,
soit environ un tiers du quota hebdomadaire. Ces durées sont une estimation : elles seront mesurées au premier
lancement.

## Fichiers produits (`/kaggle/working/train/`)

| Fichier | Contenu |
|---|---|
| `resultats/comparaison.csv` et `.md` | une ligne par modèle : AP, AUROC, seuil, rappel et précision (avec IC 95 %), F1, F2, spécificité, matrice de confusion, paramètres, temps CPU |
| `resultats/detail_par_source_et_maladie.csv` | rappel, précision et spécificité par source et par maladie |
| `resultats/pr_test.png` | courbes précision-rappel de tous les modèles sur le test |
| `resultats/choix_modele.json` | modèle retenu et règle appliquée |
| `resultats/preds/<modele>_{val,test}.csv` | score de chaque image (utilisé par le livrable 4) |
| `export/<modele>.pt` et `.json` | poids retenus, taille d'entrée, normalisation, seuil (utilisés par le livrable 5) |
| `runs/<modele>/` | historiques et points de reprise |

## Limites

- Ce notebook n'a pas encore tourné sur les vraies données : il a été testé sur un faux jeu synthétique, sur CPU,
  sans poids pré-entraînés (voir `scripts/test_train_synthetic.py`). Les valeurs par défaut (époques, lots,
  taux d'apprentissage) sont des points de départ raisonnables, non optimisés.
- Le temps CPU affiché est mesuré avec PyTorch sur le CPU de Kaggle : c'est un ordre de grandeur. Le vrai
  chronométrage (ONNX Runtime, INT8, sur ton PC) est l'objet du livrable 5.
- Sans images de drone dans le test (Cornell pas encore intégré), les scores mesurent la performance sur des photos
  rapprochées, pas en vol. L'écart de domaine sera analysé au livrable 4.
- Licences : Ultralytics est sous AGPL-3.0 (les modèles YOLO entraînés aussi). C'est sans conséquence pour un travail
  académique, mais il faudra une licence Enterprise pour un usage commercial.
