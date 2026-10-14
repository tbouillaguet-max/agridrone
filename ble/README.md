# Projet blé tendre d'hiver

Le drone survole des parcelles de blé tendre d'hiver, photographie, analyse et transmet
les résultats. Ce dossier regroupe tout ce qui est propre au blé ; le code commun,
l'installation et le téléchargement des données sont décrits dans le
[README du dépôt](../README.md).

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

## Contenu

```
ble/
  configs/
    base.yaml               hérite de configs/base.yaml ; données data/ble/, runs runs/ble/
    data/                   registre des sources (sources.yaml), empreintes (sources.lock.yaml),
                            préparation des jeux (classification*.yaml, segmentation.yaml)
    classification/         EfficientNet-B0, ConvNeXt-Tiny, modèle binaire sain / malade
    segmentation/           U-Net 5 bandes et RVB
  notebooks/                exploration des jeux préparés
  reports/                  inventaire, demandes de données, pipeline, résultats, figures
  LICENCES_DONNEES.txt      statut, licence et attribution de chaque source du blé
```

Données : `data/ble/` (raw, interim, processed). Runs : `runs/ble/<tâche>/`.

## Étapes et commandes

| Chantier | Contenu | Commande | État |
|---|---|---|---|
| 0 | Socle (structure, device, graines, configs, MLflow) | `agridrone info`, `agridrone config`, `agridrone smoke` | fait |
| 1 | Inventaire et vérification des données | — (livrables : [reports/data_inventory.md](reports/data_inventory.md), [reports/data_requests.md](reports/data_requests.md)) | fait |
| 2 | Pipeline de données : téléchargement vérifié, conversion, découpage par groupes, tuilage, augmentations, exploration | `agridrone data list\|download\|verify --project ble`, `agridrone data prepare-classification\|prepare-segmentation` ; [notebook](notebooks/01_exploration_donnees.ipynb) ; [reports/data_pipeline.md](reports/data_pipeline.md) | fait |
| 3 | Baseline YOLO11n/s pucerons (RVB, petits objets, SAHI) | — | **reporté** (pucerons mis de côté) |
| 4 | Baseline classifieur maladies du blé (EfficientNet-B0, ConvNeXt-Tiny), sortie « incertain », tests inter-sources ; modèle binaire sain / malade (§ 1.7) | `agridrone train -c ble/configs/classification/<modèle>.yaml`, `agridrone evaluate --run <run>` ; [reports/baseline_results.md](reports/baseline_results.md) § 1 | fait |
| 5 | Segmentation multispectrale N bandes vs indices (NDVI, NDRE, Otsu), ablation RVB | `agridrone train -c ble/configs/segmentation/unet_5bandes.yaml` ; [reports/baseline_results.md](reports/baseline_results.md) § 2 | fait (aucun jeu public pour le blé : chaîne validée sur WeedsGalore, inventaire § 7.2) |
| 6 | Rapport des baselines, export ONNX, temps d'inférence | `agridrone export --run <run>` ; [reports/baseline_results.md](reports/baseline_results.md) § 3 et 4 | fait (temps Jetson à mesurer sur la cible) |

Données, de bout en bout (détails dans [reports/data_pipeline.md](reports/data_pipeline.md)),
depuis la racine du dépôt :

```bash
uv run agridrone data list --project ble            # registre : sources, statut, licence
uv run agridrone data download --project ble        # tout ce qui est téléchargeable
uv run agridrone data prepare-classification        # data/ble/processed/classification/
uv run agridrone data prepare-segmentation          # data/ble/processed/segmentation/
```

L'extraction des archives RAR demande `unar` (`apt install unar` ou `brew install unar`).
Entraînement et évaluation (chantiers 4 et suivants) : la tâche est lue dans la config.

```bash
uv run agridrone train -c ble/configs/classification/efficientnet_b0.yaml num_workers=2
uv run agridrone train -c ble/configs/classification/convnext_tiny.yaml num_workers=2
uv run agridrone evaluate --run runs/ble/classification/<run> eval.target_coverage=0.8
# modèle binaire sain / malade : jeu préparé à part, puis seuil « sain très sûr »
uv run agridrone data prepare-classification --data-config ble/configs/data/classification_binaire.yaml
uv run agridrone train -c ble/configs/classification/binaire_convnext_tiny.yaml num_workers=2
uv run agridrone evaluate --run runs/ble/classification/<run> eval.max_missed_rate=0.0
uv run agridrone train -c ble/configs/segmentation/unet_5bandes.yaml num_workers=2
uv run agridrone export --run runs/ble/segmentation/<run>     # ONNX + vérification + latences
```

Chaque run écrit dans `runs/ble/<tâche>/<date>_<nom>_<empreinte>/` : `best.pt` (checkpoint
autoporteur, lisible avec `torch.load(weights_only=True)`, avec sa règle de décision),
`history.csv` / `history.png`, `eval/metrics.json`, et par ensemble évalué les
prédictions (CSV) et les matrices de confusion. Les mêmes éléments sont journalisés dans
MLflow (expérience `agridrone-ble`).

## Licences des données

Statut, licence, conditions et attribution de chaque source :
[`LICENCES_DONNEES.txt`](LICENCES_DONNEES.txt) (généré par
`uv run agridrone data licences --project ble`). Vérifications détaillées :
[reports/data_inventory.md](reports/data_inventory.md).
