# Notice — ml_dashboard, livrable 3 : adaptateurs

Module : `src\modules\ml-dashboard\ml_dashboard\adapters\` (`metrics.py`, `pytorch.py`, `ultralytics.py`, `sklearn.py`)
Version : `ml_dashboard 0.3.0`, standard `schema_version: 1`
Position dans le workflow : étape 4 (entraînement). Les adaptateurs se placent **entre** le framework d'entraînement et le RunLogger (livrable 2) : ils traduisent ce que produit chaque framework en appels `log_epoch`, `log_predictions`, `log_detection_metrics`, etc.

```
PyTorch / timm ──► PredictionCollector ──┐
Ultralytics (YOLO, RT-DETR) ─► callbacks ─┼──► RunLogger (L2) ──► dossier de run v1 ──► validate (L1)
scikit-learn ──► log_sklearn ─────────────┘
```

## 1. But

Brancher n'importe quel entraînement sur le standard en quelques lignes, sans code propre au projet. Aucun adaptateur n'importe torch ou ultralytics : ils lisent les objets de ces librairies sans en dépendre. Ils sont donc testés sans GPU.

## 2. Entrées et sorties par adaptateur

| Adaptateur | Entrées | Sorties (via le RunLogger) |
|---|---|---|
| `metrics.classification_metrics(y_true, probas, classes, label_mode, prefix, positive_class, threshold)` | indices (mono) ou matrice 0/1 (multi) ; probas (n, C) | `(métriques, par_classe)` prêts pour `log_epoch` : `acc`, `balanced_acc`, `f1_macro`, `auc`, `log_loss` (mono) ; `subset_acc`, `hamming_loss`, `f1_macro`, `f1_micro`, `auc`, `log_loss` (multi) ; `precision`, `recall` et `f1` par classe |
| `pytorch.PredictionCollector` (`for_run`, `reset`, `add`, `metrics`, `log`, `mean_loss`) + `current_lr(optimizer)` | par lot : logits (ou probas avec `from_logits=False`), cibles, ids, groupes, chemins, perte | métriques de l'époque ; `predictions/<split>.csv` |
| `ultralytics.attach_ultralytics(model, run)` | modèle `YOLO` ou `RTDETR` avant `train()` ; run de tâche `detection` ou `segmentation` | `epochs.csv`, hyperparamètres dans `config.yaml` (clé `ultralytics`), `detection/metrics.json`, `detection/pr_curves.csv`, `detection/examples/`, graphiques Ultralytics dans `artifacts/`, `model/best.pt`, `best_epoch` |
| `ultralytics.import_results_csv(run, path)` | un `results.csv` Ultralytics existant | `epochs.csv` |
| `ultralytics.log_ultralytics_metrics(run, metrics, split)` | résultat de `model.val()` | `detection/metrics.json` + `pr_curves.csv` |
| `sklearn.log_sklearn(run, estimator, X, y, split, X_train, y_train, ids, groups, paths)` | classifieur sklearn entraîné avec `predict_proba` ; y en noms ou indices | split `val` : une ligne `epoch 0` (pertes = log loss), `predictions/val.csv`, `model/model.joblib` ; split `test` : `predictions/test.csv` |

## 3. Fonctionnement

**PyTorch.** Le collecteur accumule les sorties lot par lot. Il applique softmax en mono-label et sigmoïde en multi-label. Pour un binaire avec une seule sortie, il prend la sigmoïde du logit de la classe positive. Il calcule ensuite les métriques et écrit les prédictions. Sans `ids`, les exemples sont numérotés dans l'ordre d'arrivée : il faut garder le même ordre de chargement (`shuffle=False` en validation).

**Ultralytics.** L'adaptateur a été écrit d'après le code source d'Ultralytics 8.4 et reste compatible avec les versions 8.x. Il ajoute quatre callbacks au modèle :

1. **`on_train_start`** compare les classes du `data.yaml` à celles du run, dans le même ordre. En cas de différence, il lève une `ValueError` qui **arrête l'entraînement avant la première époque** (consigne de cohérence). Il ajoute aussi tous les hyperparamètres et augmentations dans `config.yaml`, et relit le GPU.
2. **`on_train_epoch_end` puis `on_fit_epoch_end`** traduisent les clés Ultralytics : `train/box_loss` → `train_box_loss`, `metrics/mAP50-95(B)` → `val_map50_95`, `(M)` → `val_mask_*`, `lr/pg0` → `lr`. `train_loss` et `val_loss` sont la somme des composantes. Les époques sont numérotées à partir de 1, comme dans `results.csv`. L'évaluation finale d'Ultralytics rappelle `on_fit_epoch_end` sans `on_train_epoch_end` : elle est ignorée, ce n'est pas une nouvelle époque.
3. **`on_train_end`** écrit les métriques du meilleur modèle : par classe, avec le nombre d'instances et d'images, et les masques en segmentation. Il ajoute les courbes PR (101 points par classe, plus `all`), copie `best.pt`, 6 images `val_batch*_pred` au maximum et les graphiques. Il fixe enfin `best_epoch` selon la « fitness » d'Ultralytics (0,1 × mAP50 + 0,9 × mAP50-95).

`finish` n'est pas appelé par l'adaptateur : il faut utiliser `with RunLogger().start(...) as run:`. Ainsi, le statut est juste même si l'entraînement plante.

**scikit-learn.** Une baseline correspond à un run d'une seule époque (epoch 0, `lr` vide). Les colonnes de `predict_proba` sont remises dans l'ordre de `run.classes`.

## 4. Exemple Ultralytics

```python
from ultralytics import YOLO
from ml_dashboard import RunLogger
from ml_dashboard.adapters.ultralytics import attach_ultralytics

with RunLogger().start("mais", "detection", {"data": "mais.yaml"}, ["sain", "malade"],
                       model="yolov8n", framework="ultralytics",
                       datasets=[{"name": "maize-disease", "version": "v2"}]) as run:
    model = YOLO("yolov8n.pt")
    attach_ultralytics(model, run)
    model.train(data="mais.yaml", epochs=50, imgsz=640)
```

## 5. Limites (standard v1)

- Détection : un seul fichier de métriques par run. Pour évaluer le test, enregistrer `model.val(split="test")` avec `log_ultralytics_metrics(run, m, split="test")` : il **remplace** les métriques de validation.
- Les prédictions de détection boîte par boîte ne sont pas enregistrées. Le dashboard affiche donc les métriques Ultralytics telles quelles, sans les recalculer ni proposer de seuil réglable.
- YOLO en classification (`yolov8-cls`) n'est pas géré par l'adaptateur Ultralytics. Pour la classification, utiliser la boucle PyTorch, ou `import_results_csv` pour les seules courbes.
- scikit-learn : mono-label uniquement.

## 6. Cohérence avec les autres modules

- **Entrée ← datasets** : les classes du `data.yaml` sont comparées à celles du run, avec arrêt immédiat si elles diffèrent.
- **Sortie → RunLogger / validateur** : 17 tests vérifient que chaque run produit (PyTorch multi-classes, binaire à une sortie, multi-label, sklearn, YOLO détection et segmentation, RT-DETR via `results.csv`) passe `validate` sans erreur ni alerte.
- **Sortie → pipeline d'analyse (étape 5)** : **écart toujours ouvert.** Le pipeline lit le registre `pipeline\modeles.json`, dont le format est fixé par la notice du pipeline (§ E4) : `{"version": 1, "cultures": {culture: {type, onnx, classes, classe_malade | classes_malades, seuil, entree {…}, tuiles {…}}}}`. Ses types sont `classification`, `detection` (YOLOv8/v11) et `deux_etages`. Aujourd'hui, un run contient `best.pt` (ou `model.joblib`) mais ni ONNX ni entrée de registre. Correction prévue au livrable 4 : `python -m ml_dashboard export`, qui devra écrire **exactement** ce format, sinon le pipeline s'arrête sur une erreur « registre des modèles ».
- **RT-DETR** : l'adaptateur sait l'enregistrer, mais le pipeline ne l'accepte pas encore en type `detection` (point ouvert du workflow). Un RT-DETR ne sera exportable que si le pipeline l'ajoute.
- **Classes** : le registre attend `classe_malade` ou `classes_malades`. À l'export, il faudra indiquer quelles classes du run comptent comme « malade » ; par exemple, `insecte` pour un détecteur `feuille` / `insecte`.

## 7. Tests

`tests/test_adapters.py` : 16 tests, plus 1 doctest dans `ultralytics.convert_key`, soit 103 au total pour les livrables 1 à 3. Ultralytics et torch sont imités ; la séquence des callbacks reproduit `BaseTrainer._do_train` puis `final_eval` (8.4). On les lance avec `python -m pytest` depuis `src\modules\ml-dashboard`.
