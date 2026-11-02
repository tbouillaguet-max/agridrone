# agridrone — ML pour drone agricole (blé et olivier)

Briques de machine learning d'un drone autonome qui survole des cultures,
photographie, analyse et transmet les résultats. Ce dépôt ne couvre pour l'instant
**que la partie ML** (données, entraînement, évaluation, export vers l'embarqué).

Il contient **deux projets séparés**, un par culture. Chacun a son dossier, son
registre de sources, ses données, ses runs, ses rapports et son fichier de licences ;
ils ne partagent aucun jeu de données. Seul le code Python (`src/agridrone/`) est commun.

| Projet | Dossier | Contenu | État |
|---|---|---|---|
| **Blé tendre d'hiver** | [`ble/`](ble/README.md) | classifieur des maladies du blé (5 classes, et sain / malade), segmentation multispectrale N bandes, export ONNX | baselines faites ; pucerons reportés |
| **Olivier** | [`olivier/`](olivier/README.md) | inventaire des données (maladies, ravageurs, drone, fruits), TP maladies des feuilles et mouche de l'olive | inventaire et TP faits ; modèles du projet à faire |

## Structure du dépôt

```
ble/                projet blé — voir ble/README.md
  configs/          configs des expériences + registre des sources (configs/data/)
  notebooks/        exploration (aucune logique métier : elle vit dans src/)
  reports/          inventaire des données, pipeline, résultats des baselines
  LICENCES_DONNEES.txt
olivier/            projet olivier — voir olivier/README.md
  configs/          base + registre des sources (configs/data/)
  reports/          inventaire des données
  tp/               travaux pratiques (notebooks élève et corrigés)
  LICENCES_DONNEES.txt
configs/            socle commun : base.yaml, capteurs (sensors/) — voir configs/README.md
data/               données, jamais versionnées — voir data/README.md
  ble/              raw/ (téléchargements bruts), interim/ (extractions), processed/ (jeux prêts)
  olivier/          idem
runs/               sorties des entraînements, jamais versionnées : runs/ble/, runs/olivier/
src/agridrone/      code commun aux deux projets
  core/             socle : config, device, graines, environnement, runs + MLflow, projets
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

## Télécharger toutes les données sur votre PC

Chaque projet a son registre, qui liste chaque jeu avec ses liens, tailles et sommes de
contrôle : [`ble/configs/data/sources.yaml`](ble/configs/data/sources.yaml) et
[`olivier/configs/data/sources.yaml`](olivier/configs/data/sources.yaml). Une commande
télécharge, vérifie et extrait **tout ce qui est téléchargeable**, quelle que soit la
licence (projet académique non commercial) : aucune option n'est nécessaire pour
reproduire une expérience. Statut, licence et attribution de chaque jeu :
[`ble/LICENCES_DONNEES.txt`](ble/LICENCES_DONNEES.txt) et
[`olivier/LICENCES_DONNEES.txt`](olivier/LICENCES_DONNEES.txt).

1. **Installer** [Git](https://git-scm.com/downloads), [uv](https://docs.astral.sh/uv/getting-started/installation/)
   et un outil RAR (archive d'Éthiopie, quelques jeux olivier) :
   - **Windows** : [7-Zip](https://www.7-zip.org) (trouvé automatiquement dans
     `Program Files`) ; activer les chemins longs si l'extraction échoue
     (« Enable Win32 long paths »), ou cloner dans un dossier court comme `C:\agridrone` ;
   - **macOS** : `brew install unar` ;
   - **Linux** : `sudo apt install unar`.
2. **Récupérer le projet** :
   ```bash
   git clone https://github.com/tbouillaguet-max/agridrone.git
   cd agridrone/src/modules/ml-agridrone   # le projet ML est un module du monorepo
   uv sync          # installe aussi PyTorch (quelques Go)
   ```
3. **Télécharger** :
   ```bash
   uv run agridrone data list                      # jeux, statut, licence, taille (les deux projets)
   uv run agridrone data download                  # tout (blé et olivier)
   uv run agridrone data download --project ble    # un seul projet : ble ou olivier
   uv run agridrone data download --no-extract     # archives seules, sans extraction
   uv run agridrone data verify                    # revérifie les sommes de contrôle
   ```
   Les fichiers vont dans `data/ble/` et `data/olivier/`. La commande reprend là où elle
   s'est arrêtée : un fichier déjà présent et conforme n'est pas retéléchargé. Les jeux
   marqués « manuel » (formulaire, compte, accord, ou dépôt qui refuse les accès
   automatisés) sont listés avec leur lien dans le `LICENCES_DONNEES.txt` du projet.

**Espace disque.** La commande vérifie l'espace libre avant de commencer.

| Projet | Archives | Avec extraction (environ) | Plus gros jeux |
|---|---|---|---|
| Blé (`--project ble`) | 36,8 Go + Yellow-Rust-19 (1,55 Go déclarés) | 80 Go | Agriculture-Vision 21 Go |
| Olivier (`--project olivier`) | 137 Go + quelques jeux Kaggle et git de taille inconnue (au moins 1,3 Go) | 270 Go | images brutes ICAERUS 72 Go, SPADE 15 Go |

`--no-extract` ne garde que les archives. Pour mettre les données d'un projet sur un
autre disque, créer par exemple `olivier/configs/local.yaml` (ignoré par git) :

```yaml
_base_: base.yaml
paths: {raw: "D:/agridrone/olivier/raw", interim: "D:/agridrone/olivier/interim", processed: "D:/agridrone/olivier/processed"}
```

puis ajouter `--project olivier -c olivier/configs/local.yaml` à chaque commande `data`
(même chose pour le blé avec `ble/configs/local.yaml` et `--project ble`).

`uv run agridrone data list --files` affiche le lien direct de chaque fichier, pour un
téléchargement à la main dans un navigateur.

## Socle commun : device, graines, configs, suivi

- **Device** (`agridrone.core.device`) : `device: auto` choisit CUDA, puis MPS,
  puis CPU. Une demande explicite indisponible (`cuda`, `mps`) **échoue** au lieu
  de basculer en silence sur CPU.
- **Graines** (`agridrone.core.seed`) : `seed_everything` fixe Python, NumPy et
  PyTorch ; `seed_worker` + `make_generator` rendent les DataLoader
  reproductibles. `deterministic: true` active les algorithmes déterministes
  PyTorch (plus lent ; à réserver aux runs de référence).
- **Configs** (`agridrone.core.config`) : YAML avec héritage, surcharges
  `cle.sous_cle=valeur`, validation pydantic stricte (une faute de frappe dans
  une clé est une erreur). `configs/base.yaml` est commun ; `ble/configs/base.yaml`
  et `olivier/configs/base.yaml` en héritent et fixent les dossiers du projet.
  Détails dans [configs/README.md](configs/README.md).
- **Projets** (`agridrone.core.paths.PROJECTS`) : emplacement de la config, du
  registre, du fichier d'empreintes et du fichier de licences de chaque projet.
- **Runs** (`agridrone.core.run`) : chaque run crée
  `runs/<projet>/<tâche>/<date>_<nom>_<hash>/` avec la config résolue (`config.yaml`) et
  l'environnement (`environment.json` : commit git, état modifié, versions,
  device). Ces fichiers et la config aplatie sont journalisés dans **MLflow**
  (base `mlflow.db`, artefacts `mlartifacts/`, tous deux ignorés par git ; une
  expérience par projet : `agridrone-ble`, `agridrone-olivier`).

```bash
uv run agridrone config -c configs/base.yaml seed=1 device=cpu   # config résolue + empreinte
uv run agridrone smoke seed=1                                     # mini-entraînement suivi dans MLflow
uv run mlflow ui --backend-store-uri sqlite:///mlflow.db          # interface : http://127.0.0.1:5000
```

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
- **Données** : projet **académique, non commercial** (confirmé le 12 octobre 2026). Les
  jeux sous licence non commerciale sont donc téléchargés et utilisables comme les
  autres. Statut, licence, conditions et attribution de chaque jeu, par projet :
  [`ble/LICENCES_DONNEES.txt`](ble/LICENCES_DONNEES.txt) et
  [`olivier/LICENCES_DONNEES.txt`](olivier/LICENCES_DONNEES.txt) (générés depuis les
  registres par `uv run agridrone data licences`) ; vérifications détaillées :
  [ble/reports/data_inventory.md](ble/reports/data_inventory.md) et
  [olivier/reports/data_inventory.md](olivier/reports/data_inventory.md). Si le projet
  devenait commercial, il faudrait réentraîner sans les jeux « non commercial ».
- **Poids pré-entraînés** (timm : EfficientNet-B0, ConvNeXt-Tiny, ResNet-18) : publiés sous
  Apache-2.0. Ils sont appris sur ImageNet, dont les images ne sont accessibles que pour
  un usage non commercial. Le statut juridique des poids qui en dérivent n'est pas
  tranché : à faire valider avant commercialisation.
- **Export** : onnx (Apache-2.0), onnxscript et onnxruntime (MIT).

## Qualité

```bash
uv run pytest            # tests (dont un test MLflow marqué `slow` ; -m "not slow" pour l'exclure)
uv run ruff check . && uv run ruff format --check .
uv run mypy              # typage strict de src/
```
