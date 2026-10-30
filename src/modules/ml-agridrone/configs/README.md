# Configs

Une expérience = un fichier YAML. Ce dossier contient le **socle commun** aux deux
projets ; les configs propres à une culture sont dans `ble/configs/` et
`olivier/configs/`.

| Fichier | Contenu |
|---|---|
| `configs/base.yaml` | graine, device, chemins par défaut, MLflow (commun) |
| `configs/sensors/` | définition des bandes par capteur (RVB, multispectral N bandes) |
| `ble/configs/base.yaml` | hérite du socle ; données dans `data/ble/`, runs dans `runs/ble/`, expérience MLflow `agridrone-ble` |
| `olivier/configs/base.yaml` | hérite du socle ; données dans `data/olivier/`, runs dans `runs/olivier/`, expérience MLflow `agridrone-olivier` |

Les configs de tâche héritent de la base de leur projet :

```yaml
# ble/configs/classification/convnext_tiny.yaml
_base_: base.yaml             # chemin relatif à ce fichier (ou liste de chemins)
name: convnext_tiny
model:
  arch: convnext_tiny.fb_in22k_ft_in1k
```

`task` (ici `classification`, hérité de `ble/configs/classification/base.yaml`) choisit
le schéma de validation et le lanceur : `uv run agridrone train -c <config>`.

- **Fusion** : les sections (dictionnaires) sont fusionnées récursivement ; les
  listes et valeurs simples sont remplacées.
- **Surcharges** en ligne de commande, après les options :
  `uv run agridrone config -c configs/base.yaml seed=1 tracking.enabled=false`.
  Les valeurs sont lues en YAML (`1e-3` donne un float, `[1, 2]` une liste).
- **Validation stricte** : une clé inconnue (faute de frappe) fait échouer le
  chargement. Chaque tâche déclare son schéma pydantic
  (`agridrone.core.config.register_task_schema`).
- **Reproductibilité** : chaque run écrit la config résolue (`config.yaml`) et
  son empreinte SHA-256 dans `runs/<projet>/<tâche>/<date>_<nom>_<hash>/`, avec
  l'état git et les versions des paquets (`environment.json`). Ces fichiers sont
  aussi attachés au run MLflow.

Configs du projet blé (`ble/configs/`) :

| Dossier | Contenu | Chantier |
|---|---|---|
| `base.yaml` | chemins `data/ble/`, `runs/ble/` | 0 |
| `data/` | registre des sources (`sources.yaml`, `sources.lock.yaml`), préparation des jeux ; `classification_binaire.yaml` : jeu sain / malade | 2 |
| `detection/` | YOLO11 pucerons (à créer : chantier reporté) | 3 |
| `classification/` | classifieur maladies du blé : `base.yaml` (données, règle de décision), `efficientnet_b0.yaml`, `convnext_tiny.yaml`, `binaire_convnext_tiny.yaml` (sain / malade) | 4 |
| `segmentation/` | U-Net N bandes et baselines par indices : `base.yaml`, `unet_5bandes.yaml`, `unet_rvb.yaml` | 5 |

Configs du projet olivier (`olivier/configs/`) :

| Dossier | Contenu |
|---|---|
| `base.yaml` | chemins `data/olivier/`, `runs/olivier/` |
| `data/` | registre des sources (`sources.yaml`, `sources.lock.yaml`) et listes de fichiers (`manifests/`) |

Les TP olivier (`olivier/tp/`) sont des notebooks autonomes : ils n'utilisent pas
encore ces configs, seulement les dossiers `data/olivier/` et `runs/olivier/`.
