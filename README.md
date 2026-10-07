# agridrone — ML pour drone agricole (blé tendre d'hiver)

Briques de machine learning d'un drone autonome qui survole des parcelles de blé
tendre d'hiver, photographie, analyse et transmet les résultats. Ce dépôt ne
couvre pour l'instant **que la partie ML** (données, entraînement, évaluation,
export vers l'embarqué).

## Architecture cible

```
                        ┌─────────────────────────────────────────────┐
  Caméra multispectrale │ NIVEAU PARCELLE                             │
  (N bandes, GeoTIFF) ──▶ orthophoto ─▶ tuiles N bandes ─▶ segmentation│──▶ carte des zones
                        │                 (U-Net smp, entrée N canaux) │    stressées / malades
                        └─────────────────────────────────────────────┘
                        ┌─────────────────────────────────────────────┐
  Caméra RVB haute      │ NIVEAU PLANTE                               │
  résolution (vol bas) ─▶ image ─┬▶ détecteur YOLO (pucerons, insectes)│──▶ comptages,
                        │        └▶ classifieur (état feuille / épi)  │    diagnostics
                        └─────────────────────────────────────────────┘
```

- **Niveau parcelle** : segmentation de tuiles d'orthophoto multispectrale.
  Règle : on n'entraîne le multispectral **que** sur des tâches disposant de
  données publiques vérifiées ; le code est générique en nombre de bandes
  (3, 4, 5… N) pour accueillir plus tard le jeu de données du drone.
- **Niveau plante** : détection de petits objets (pucerons) par YOLO sur
  images RVB haute résolution, et classification de l'état sanitaire
  (sain / maladies) par transfer learning timm.

## Structure du dépôt

```
configs/            configs YAML (héritage `_base_`, surcharges en CLI) — voir configs/README.md
data/               données, jamais versionnées — voir data/README.md
                    (registre des sources et empreintes : configs/data/)
  raw/              téléchargements bruts (immuables)
  interim/          extractions / conversions intermédiaires
  processed/        jeux prêts à l'entraînement + fichiers de découpage
notebooks/          exploration (aucune logique métier : elle vit dans src/)
reports/            inventaire des données, résultats des baselines
src/agridrone/
  core/             socle : config, device, graines, environnement, runs + MLflow
  data/             téléchargement, conversion, découpage, tuilage, augmentations
  models/           YOLO, classifieurs timm, U-Net N bandes
  training/         lanceurs d'entraînement
  eval/             métriques, analyses d'erreurs
  export/           ONNX, mesure du temps d'inférence
  cli.py            point d'entrée `agridrone`
tests/              tests (pytest)
```

## Installation

Prérequis : [uv](https://docs.astral.sh/uv/) ≥ 0.9. Python 3.12 est installé
automatiquement par uv si absent.

```bash
uv sync                     # dépendances + outils de dev (pytest, ruff, mypy)
uv sync --group notebooks   # + JupyterLab
uv run agridrone info       # device détecté, versions, état git
uv run agridrone smoke      # run de vérification de bout en bout (voir plus bas)
```

**PyTorch et GPU.** `uv sync` installe torch depuis PyPI :

- **Linux + GPU NVIDIA** : la wheel PyPI de torch 2.14 est compilée pour CUDA 13.0
  (`+cu130`), ce qui impose un pilote NVIDIA de la branche 580 ou plus récente
  (`nvidia-smi` pour vérifier). Avec un pilote plus ancien, utiliser une build de
  torch pour votre version de CUDA : déclarer l'index PyTorch correspondant dans
  `pyproject.toml` (`[[tool.uv.index]]` + `[tool.uv.sources]`, voir la
  [doc uv « PyTorch »](https://docs.astral.sh/uv/guides/integration/pytorch/)).
- **macOS Apple Silicon** : la wheel PyPI inclut MPS ; `device: auto` le sélectionne.
- **Windows** : la wheel PyPI est CPU uniquement ; même procédure d'index que
  ci-dessus pour CUDA.
- **CPU seul** : fonctionne tel quel (wheel plus lourde que nécessaire, sans gêne).

## Socle : device, graines, configs, suivi

- **Device** (`agridrone.core.device`) : `device: auto` choisit CUDA, puis MPS,
  puis CPU. Une demande explicite indisponible (`cuda`, `mps`) **échoue** au lieu
  de basculer en silence sur CPU.
- **Graines** (`agridrone.core.seed`) : `seed_everything` fixe Python, NumPy et
  PyTorch ; `seed_worker` + `make_generator` rendent les DataLoader
  reproductibles. `deterministic: true` active les algorithmes déterministes
  PyTorch (plus lent ; à réserver aux runs de référence).
- **Configs** (`agridrone.core.config`) : YAML avec héritage, surcharges
  `cle.sous_cle=valeur`, validation pydantic stricte (une faute de frappe dans
  une clé est une erreur). Détails dans [configs/README.md](configs/README.md).
- **Runs** (`agridrone.core.run`) : chaque run crée
  `runs/<tâche>/<date>_<nom>_<hash>/` avec la config résolue (`config.yaml`) et
  l'environnement (`environment.json` : commit git, état modifié, versions,
  device). Ces fichiers et la config aplatie sont journalisés dans **MLflow**
  (base `mlflow.db`, artefacts `mlartifacts/`, tous deux ignorés par git).

```bash
uv run agridrone config -c configs/base.yaml seed=1 device=cpu   # config résolue + empreinte
uv run agridrone smoke seed=1                                     # mini-entraînement suivi dans MLflow
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db          # interface : http://127.0.0.1:5000
```

## Étapes du projet et commandes

| Chantier | Contenu | Commande | État |
|---|---|---|---|
| 0 | Socle (structure, device, graines, configs, MLflow) | `agridrone info`, `agridrone config`, `agridrone smoke` | fait |
| 1 | Inventaire et vérification des données | — (livrables : [reports/data_inventory.md](reports/data_inventory.md), [reports/data_requests.md](reports/data_requests.md)) | fait |
| 2 | Pipeline de données : téléchargement vérifié, conversion, découpage par groupes, tuilage, augmentations, exploration | `agridrone data list\|download\|verify\|prepare-classification\|prepare-segmentation` ; [notebook](notebooks/01_exploration_donnees.ipynb) ; [reports/data_pipeline.md](reports/data_pipeline.md) | fait |
| 3 | Baseline YOLO11n/s pucerons (RVB, petits objets, SAHI) | — | **reporté** (pucerons mis de côté) |
| 4 | Baseline classifieur maladies du blé (EfficientNet-B0, ConvNeXt-Tiny), sortie « incertain », tests inter-sources | `agridrone train -c configs/classification/<modèle>.yaml`, `agridrone evaluate --run <run>` ; [reports/baseline_results.md](reports/baseline_results.md) § 1 | fait |
| 5 | Segmentation multispectrale N bandes vs indices (NDVI, NDRE, Otsu) | `agridrone train -c configs/segmentation/unet_5bandes.yaml` | aucun jeu public pour le blé : chaîne validée sur WeedsGalore (inventaire, §7.2) |
| 6 | Rapport des baselines, export ONNX, temps d'inférence | `agridrone export --run <run>` | code prêt |

Données, de bout en bout (détails dans [reports/data_pipeline.md](reports/data_pipeline.md)) :

```bash
uv run agridrone data list                          # registre : sources, statut, licence
uv run agridrone data download --include-candidates # téléchargement vérifié + extraction
uv run agridrone data prepare-classification        # data/processed/classification/
uv run agridrone data prepare-segmentation          # data/processed/segmentation/
```

L'extraction des archives RAR demande `unar` (`apt install unar` ou `brew install unar`).
Entraînement et évaluation (chantiers 4 et suivants) : la tâche est lue dans la config.

```bash
uv run agridrone train -c configs/classification/efficientnet_b0.yaml num_workers=2
uv run agridrone train -c configs/classification/convnext_tiny.yaml num_workers=2
uv run agridrone evaluate --run runs/classification/<run> eval.target_coverage=0.8
```

Chaque run écrit dans `runs/<tâche>/<date>_<nom>_<empreinte>/` : `best.pt` (checkpoint
autoporteur, lisible avec `torch.load(weights_only=True)`, avec sa règle de décision),
`history.csv` / `history.png`, `eval/metrics.json`, et par ensemble évalué les
prédictions (CSV) et les matrices de confusion. Les mêmes éléments sont journalisés dans
MLflow.

## Licences : points d'attention

- **Ultralytics (YOLO11) est sous AGPL-3.0.** D'après sa
  [page de licences](https://www.ultralytics.com/license), Ultralytics exige une
  licence *Enterprise* pour tout produit commercial dont le code n'est pas publié,
  y compris un déploiement embarqué (edge, robotique, caméras). Alternatives dont
  le code et les poids sont publiés sous Apache-2.0 : D-FINE, RF-DETR. Les
  baselines restent en YOLO11, comme demandé ; le choix final du détecteur est à
  trancher avant toute industrialisation.
- **Albumentations** est figé en version 2.0.8, la dernière publiée sous licence
  MIT. Son successeur `albumentationsx` est sous AGPL-3.0.
- **Données** : la licence de chaque jeu de données (usage commercial ou non) est
  vérifiée dans [reports/data_inventory.md](reports/data_inventory.md).

## Qualité

```bash
uv run pytest            # tests (dont un test MLflow marqué `slow` ; -m "not slow" pour l'exclure)
uv run ruff check . && uv run ruff format --check .
uv run mypy              # typage strict de src/
```
