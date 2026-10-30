# Standard de run `ml_dashboard` — `schema_version: 1`

Ce document définit le format **unique** qu'un entraînement doit produire pour
être lu par le dashboard, quel que soit le projet ou le framework (PyTorch,
timm, Ultralytics YOLO / RT-DETR, scikit-learn).

- Les règles marquées **DOIT** sont vérifiées par
  `python -m ml_dashboard validate <dossier>` (erreur si violées).
- Les règles marquées **DEVRAIT** produisent une alerte.
- Les schémas JSON formels sont dans `ml_dashboard/schemas/`.
- Les constantes côté code sont dans `ml_dashboard/standard.py`.

---

## 1. Principe

Un run est un **dossier autonome**. Le dashboard **recalcule** toutes les
métriques d'évaluation (matrice de confusion, ROC, PR, calibration, métriques
selon le seuil) à partir des **prédictions brutes** (`predictions/*.csv`).
Il ne s'appuie jamais sur des images figées ; c'est ce qui rend le seuil
de décision réglable à l'affichage.

Les figures propres à un projet (Grad-CAM, galeries…) vont dans `artifacts/`,
les tableaux libres dans `extra_results/` : le dashboard les affiche sans
code spécifique.

## 2. Arborescence

```
runs/<projet>/<run_id>/
├── meta.json            # DOIT   métadonnées
├── config.yaml          # DOIT   hyperparamètres et augmentations
├── classes.json         # DOIT   classes ordonnées
├── epochs.csv           # DOIT   une ligne par époque
├── predictions/         # classification uniquement
│   ├── val.csv          # DOIT si status = completed
│   └── test.csv         # optionnel, écrit UNE fois en fin de run
├── detection/           # détection / segmentation uniquement
│   ├── metrics.json     # DOIT si status = completed
│   ├── pr_curves.csv    # optionnel
│   └── examples/        # optionnel : images de prédictions
├── artifacts/           # optionnel : figures libres
│   └── manifest.json    # DOIT si artifacts/ contient des fichiers
├── extra_results/       # optionnel : tableaux CSV libres (+ manifest.json optionnel)
└── model/               # DEVRAIT contenir le meilleur checkpoint (+ ONNX optionnel)
```

Tout autre élément à la racine du run déclenche une alerte et est ignoré.

**Encodage** : tous les fichiers texte sont en **UTF-8** (attention, Windows
écrit en cp1252 par défaut : toujours passer `encoding="utf-8"`).
**CSV** : séparateur `,`, point décimal `.`, première ligne = en-tête,
cellule vide = valeur manquante.

## 3. Identifiants

| Élément | Format | Exemple |
|---|---|---|
| `<projet>` | `^[a-z0-9][a-z0-9_-]{0,63}$` | `plantes-maladies` |
| `<run_id>` | `AAAAMMJJ_HHMMSS_<nomcourt>`, nomcourt au format projet | `20261029_180500_effnet-b0` |
| nom de classe | sans `,`, sans `\|`, sans retour ligne, sans espace en bord | `carence eau` |

- `meta.run_id` **DOIT** être égal au nom du dossier.
- `meta.project` **DEVRAIT** être égal au nom du dossier parent.
- `standard.make_run_id("EffNet B0")` produit un identifiant conforme.

## 4. `meta.json`

Schéma : `schemas/meta.schema.json`. Aucune clé hors liste (utiliser `extra`).

| Clé | Type | Rôle |
|---|---|---|
| `schema_version` | `1` | version du standard |
| `run_id`, `project` | chaîne | voir §3 |
| `task` | `classification` \| `detection` \| `segmentation` | |
| `model` | chaîne | `efficientnet_b0`, `yolov8n-seg`, `rtdetr-l`… |
| `framework` | chaîne | `pytorch`, `ultralytics`, `sklearn`… |
| `seed` | entier \| null | graine |
| `status` | `running` \| `completed` \| `failed` \| `interrupted` | |
| `created_at` | date ISO 8601 | début |
| `ended_at`, `duration_s` | date \| null, nombre \| null | DEVRAIENT être remplis si `completed` |
| `best_epoch`, `monitor` | optionnels | époque du checkpoint et colonne surveillée (`val_loss`…) |
| `environment` | objet | `host` (`kaggle`/`local`…), `python`, `platform`, `gpu` (null = CPU), `libraries` `{nom: version}` |
| `datasets` | liste | `{name, version, root?, n_samples?}` ; `version` permet de retrouver les données exactes |
| `tags`, `notes`, `extra` | optionnels | libres |

`datasets[].root` sert de racine aux `image_path` relatifs des prédictions.

## 5. `config.yaml`

Un dictionnaire YAML à la racine, sans autre contrainte. Il **DEVRAIT**
contenir *tous* les hyperparamètres et augmentations : le comparateur de runs
affiche les différences clé par clé (les dictionnaires imbriqués sont
aplatis en `augment.flip`, `optimizer.lr`…).

## 6. `classes.json`

Schéma : `schemas/classes.schema.json`.

```json
{
  "schema_version": 1,
  "label_mode": "single",
  "classes": ["sain", "malade"],
  "positive_class": "malade"
}
```

- `classes` : liste **ordonnée** ; l'indice d'une classe est celui de la
  sortie du modèle.
- `label_mode` :
  - `single` — **mono-label** : une image appartient à exactement une classe ;
  - `multi` — **multi-label** : une image appartient à 0, 1 ou plusieurs
    classes (classification uniquement).
- `positive_class` : obligatoire en pratique pour un binaire mono-label
  (sinon alerte, le dashboard prend `classes[1]`) ; **DOIT** être `null`
  sinon.
- Détection / segmentation : `classes` liste les classes d'objets,
  `label_mode = "single"`, `positive_class = null`.

## 7. `epochs.csv`

| Colonne | Obligatoire | Contenu |
|---|---|---|
| `epoch` | oui | entier ≥ 0, strictement croissant |
| `lr` | oui | taux d'apprentissage (≥ 0) en fin d'époque |
| `train_loss` | oui | perte moyenne d'entraînement |
| `val_loss` | oui | perte de validation (vide si non calculée) |
| `train_<métrique>` / `val_<métrique>` | non | métriques libres, en minuscules : `val_acc`, `val_f1_macro`, `val_auc`… |
| `<split>_<métrique>__<classe>` | non | métrique par classe : `val_recall__mildiou` |

Motif exact des colonnes libres :
`^(train|val)_[a-z0-9]+(_[a-z0-9]+)*(__<classe>)?$`.

- Les métriques de **test ne vont jamais** dans `epochs.csv` (le test n'est
  évalué qu'une fois, voir §8).
- Un run `completed` **DOIT** avoir au moins une ligne. Une baseline
  scikit-learn écrit une seule ligne `epoch = 0`.
- Détection : `train_loss` / `val_loss` = somme des composantes ; les
  composantes et les métriques suivent la convention (`train_box_loss`,
  `val_cls_loss`, `val_precision`, `val_recall`, `val_map50`,
  `val_map50_95`, et `val_mask_map50`… en segmentation). Les noms
  Ultralytics sont convertis par l'adaptateur (livrable 3).

## 8. `predictions/<split>.csv` (classification)

`split` ∈ {`val`, `test`}. Une ligne par exemple.

| Colonne | Contenu |
|---|---|
| `id` | identifiant unique et non vide de l'exemple |
| `group` | groupe pour l'analyse et les fuites (parcelle, vol, plante…) ; peut être vide |
| `y_true` | vérité terrain (voir ci-dessous) |
| `y_pred` | prédiction au seuil par défaut |
| `image_path` | chemin de l'image (absolu, ou relatif à `datasets[].root`) ; peut être vide |
| `proba_<classe>` | une colonne par classe de `classes.json`, valeur dans [0, 1] |

**Mono-label** (`label_mode = single`)
- `y_true`, `y_pred` : un nom de classe.
- Les `proba_*` d'une ligne **DOIVENT** sommer à 1 (± 1e-3) : sorties softmax.
- `y_pred` **DEVRAIT** être la classe de proba maximale.

**Multi-label** (`label_mode = multi`)
- `y_true`, `y_pred` : noms de classes séparés par `|`, cellule vide =
  aucune classe (ex. `mildiou|carence eau`).
- Les `proba_*` sont **indépendantes** (sorties sigmoïdes), sans contrainte
  de somme.
- `y_pred` **DEVRAIT** correspondre au seuil 0,5 par classe.

**Règles communes**
- `val.csv` **DOIT** exister pour un run `completed`.
- `test.csv` est écrit **une seule fois**, en fin de run : il **DOIT** être
  absent tant que `status ≠ completed`. Le dashboard l'affiche à part, et
  seulement s'il existe.
- Les classes de `y_true` / `y_pred` **DOIVENT** exister dans
  `classes.json` ; aucune colonne `proba_*` en trop.
- Colonnes supplémentaires : tolérées (alerte), ignorées par le dashboard.

## 9. `detection/` (détection et segmentation)

**`metrics.json`** (schéma `schemas/detection_metrics.schema.json`) :
métriques finales du meilleur modèle, en **fractions** dans [0, 1].

```json
{
  "schema_version": 1,
  "split": "val",
  "box":  {"precision": 0.71, "recall": 0.64, "map50": 0.58, "map50_95": 0.33},
  "mask": null,
  "per_class": [
    {"class": "insecte", "n_images": 120, "n_instances": 340,
     "precision": 0.70, "recall": 0.61, "map50": 0.55, "map50_95": 0.30}
  ]
}
```

`mask` reprend les clés de `box` en segmentation (alerte s'il manque).

**`pr_curves.csv`** (optionnel) : format long, colonnes `class`, `recall`,
`precision` (+ `kind` = `box`/`mask` optionnel) ; `class = all` autorisé
pour la courbe globale.

**`examples/`** (optionnel) : images de prédictions annotées.

## 10. `artifacts/` et `extra_results/`

Schéma des manifests : `schemas/manifest.schema.json`.

```json
{
  "schema_version": 1,
  "items": [
    {"file": "gradcam_mildiou.png", "title": "Grad-CAM — mildiou",
     "description": "10 erreurs les plus confiantes", "kind": "image"}
  ]
}
```

- `artifacts/` : images (`.png .jpg .jpeg .gif .svg .webp`) ou pages `.html`.
  `manifest.json` **DOIT** exister dès qu'il y a un fichier ; chaque entrée
  **DOIT** pointer un fichier existant du dossier ; un fichier non listé
  produit une alerte.
- `extra_results/` : uniquement des `.csv` ; `manifest.json` optionnel (à
  défaut, le titre est le nom du fichier).
- `file` : chemin relatif, séparateur `/`, sans sortir du dossier.

## 11. `model/`

Meilleur checkpoint (nom libre, ex. `best.pt`) et export ONNX optionnel
(`model.onnx`). Alerte si vide pour un run `completed`.

## 12. Versionnement et rétrocompatibilité

- Chaque JSON porte `schema_version` ; `meta.json` fait foi pour le run.
- **Toute** modification du standard (fichier, colonne, clé, règle)
  incrémente `SCHEMA_VERSION` dans `standard.py` et ce document reçoit une
  section « Changements depuis la version N-1 ».
- Le code lit toutes les versions listées dans `SUPPORTED_SCHEMA_VERSIONS` ;
  une version plus récente que le code est refusée avec un message
  demandant de mettre à jour `ml_dashboard`.
- Les anciennes versions restent lisibles (migration à la lecture), jamais
  réécrites sur disque.

## 13. Validation

```bash
python -m ml_dashboard validate <run | dossier de projet | dossier central>
python -m ml_dashboard validate runs --quiet     # seulement les runs à problème
python -m ml_dashboard validate runs --strict    # les alertes font échouer
python -m ml_dashboard validate runs --json      # sortie machine
```

Codes de sortie : `0` tout est valide, `1` au moins un run invalide,
`2` aucun run trouvé.
