# Notice — ml_dashboard, livrable 2 : RunLogger

Module : `src\modules\ml-dashboard\ml_dashboard\logger.py` (+ `_io.py`)
Version : `ml_dashboard 0.2.0`, standard `schema_version: 1`
Position dans le workflow : étape 4 (entraînement). Le RunLogger est appelé **dans** la boucle d'entraînement (Kaggle ou local) ; il produit le dossier de run que lisent le validateur (livrable 1), l'import (livrable 4) et le dashboard (livrable 5).

```
Boucle d'entraînement ──► [RunLogger] ──► runs/<projet>/<run_id>/  ──► validate (L1) ──► dashboard (L5)
   (Kaggle / local)                  └──► <projet>__<run_id>.zip (Kaggle) ──► import (L4) ──► runs\ central
```

## 1. But

Écrire, depuis n'importe quelle boucle d'entraînement, un dossier de run **conforme au standard v1** sans que l'utilisateur ait à connaître le format. Le logger refuse immédiatement (`ValueError`) toute donnée non conforme, pour que l'erreur apparaisse à la première époque et pas après des heures de GPU.

## 2. Entrées

| Méthode | Entrées | Ce qui est vérifié tout de suite |
|---|---|---|
| `RunLogger(root, archive, archive_dir, verbose)` | dossier central (optionnel) | — |
| `start(project, task, config, classes, *, model, framework, label_mode, positive_class, seed, datasets, name, monitor, monitor_mode, tags, notes, extra)` | config = dict, dataclass ou Namespace ; classes ordonnées | tâche, label_mode, noms de classes (ni `,` ni `\|`), positive_class, schéma de meta.json (dont `datasets[].version`) |
| `log_epoch(epoch, *, per_class, **metriques)` | `lr`, `train_loss`, `val_loss`, puis `train_*` / `val_*` ; float, numpy ou tenseur 0-d | époque entière strictement croissante ; noms en minuscules ; pas de `test_*` ; valeurs numériques |
| `log_predictions(split, ids, y_true, probas, groups, paths, *, y_pred)` | probas après softmax (mono) ou sigmoïde (multi) ; binaire : vecteur de la classe positive accepté ; y_true en noms, indices, matrice 0/1 (multi) ou `"a\|b"` | forme (n, C) ; probas dans [0, 1] (sinon « logits ? ») ; somme = 1 en mono ; classes connues ; ids uniques et non vides ; test une seule fois |
| `log_artifact(obj, title, description, *, filename)` | figure matplotlib, figure plotly, image PIL, tableau numpy / tenseur (HWC ou CHW), chemin d'image ou HTML | type et extension affichables |
| `log_table(name, table, *, title, description)` | DataFrame, dict ou liste de dicts | — |
| `log_model(source, *, filename, best_epoch)` | chemin de fichier, objet avec `state_dict()`, ou bytes | fichier existant |
| `log_detection_metrics(box, per_class, *, mask, split)` | métriques finales en fractions | schéma (refuse `70` au lieu de `0.70`), classes connues |
| `log_pr_curves(df)`, `log_detection_example(image, name)` | courbes PR ; image annotée | colonnes, classes |
| `finish(status, *, archive)` | `completed`, `failed` ou `interrupted` | — |

**Où le run est écrit** (premier critère rempli) : argument `root` → variable d'environnement `ML_DASHBOARD_RUNS` → sur Kaggle `/kaggle/working/runs` → sinon `.\runs`.

## 3. Sorties

- Le dossier `runs/<projet>/<AAAAMMJJ_HHMMSS_nomcourt>/` au format de `STANDARD.md` : `meta.json`, `config.yaml`, `classes.json`, `epochs.csv`, `predictions/`, `detection/`, `artifacts/` + `manifest.json`, `extra_results/` + `manifest.json`, `model/`.
- `meta.json` rempli automatiquement : hôte (kaggle/colab/local), Python, plateforme, GPU (si torch est importé), versions des librairies, durée, statut, meilleure époque (`best_epoch`) si `monitor` est donné.
- `finish` renvoie le `ValidationReport` du livrable 1 et l'affiche. Il **ne lève pas** d'exception si le run est invalide, pour ne jamais perdre un entraînement long à cause d'un détail de format.
- Sur Kaggle (ou avec `archive=True`) : `/kaggle/working/<projet>__<run_id>.zip`, dont les chemins internes commencent par `<projet>/<run_id>/`. C'est l'entrée de la commande `import` (livrable 4).

## 4. Fonctionnement

1. `start` crée le dossier (suffixe `-2`, `-3`… si deux runs démarrent dans la même seconde), écrit config, classes, meta (`status: running`) et un `epochs.csv` vide.
2. `log_epoch` ajoute la ligne en mémoire puis réécrit tout `epochs.csv` : une métrique apparue en cours de route devient une nouvelle colonne. Si `monitor` est réglé, `best_epoch` est mis à jour ; `run.is_best_epoch` indique quand sauver le checkpoint.
3. `log_predictions("val", …)` réécrit `val.csv` à chaque appel. `log_predictions("test", …)` écrit dans `.pending/test.csv`. Ce fichier n'est publié dans `predictions/` qu'au `finish("completed")` : un run planté ne publie jamais de résultat de test.
4. Toutes les écritures passent par un fichier temporaire suivi d'un renommage. Si Kaggle coupe le notebook, le fichier précédent reste intact.
5. `finish` publie le test, renseigne `ended_at`, `duration_s` et `status`, valide le run, puis crée l'archive.
6. Utilisé avec `with RunLogger().start(...) as run:`, le bloc appelle `finish` tout seul. Le statut vaut `completed` en sortie normale, `interrupted` sur Ctrl+C et `failed` sur une exception (le message est noté dans `notes`). L'exception n'est jamais masquée.

En multi-GPU (DDP), n'appeler le logger que sur le processus de rang 0.

## 5. Exemple

```python
from ml_dashboard import RunLogger

with RunLogger().start("plantes", "classification", config, ["sain", "malade"],
                       model="efficientnet_b0", framework="pytorch", seed=42,
                       datasets=[{"name": "plantvillage", "version": "v3"}],
                       monitor="val_loss") as run:
    for epoch in range(n_epochs):
        ...
        run.log_epoch(epoch, lr=lr, train_loss=tl, val_loss=vl, val_acc=acc,
                      per_class={"val_recall": {"sain": r0, "malade": r1}})
        if run.is_best_epoch:
            run.log_model(model)                     # -> model/best.pt
    run.log_predictions("val", ids, y_true, probas, groupes, chemins)
    run.log_predictions("test", ids_t, y_true_t, probas_t)  # une seule fois, en fin de run
```

## 6. Cohérence avec les autres modules

- **Entrée ← boucle d'entraînement** : aucune contrainte de framework ; tenseurs torch acceptés sans dépendance à torch.
- **Sortie → validateur (L1)** : 41 tests vérifient que chaque run produit (binaire, multi-classes, multi-label, détection, run planté, run interrompu) passe `validate` sans erreur.
- **Sortie → pipeline d'analyse (étape 5)** : **écart ouvert.** Le pipeline attend un ONNX + une entrée dans `modeles.json` (`{culture: {type, onnx, classes, seuil}}`). Le RunLogger range le checkpoint dans `model/` mais ne produit pas `modeles.json`. Correction prévue au livrable 4 : une commande `python -m ml_dashboard export <run> --culture <ble|mais|pommier>`.

## 7. Tests

`tests/test_logger.py` : 41 tests (86 au total avec le livrable 1). On les lance avec `python -m pytest` depuis `src\modules\ml-dashboard`.
