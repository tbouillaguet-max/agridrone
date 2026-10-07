# Configs

Une expérience = un fichier YAML. Les configs de tâche héritent de `base.yaml` :

```yaml
# configs/<tâche>/<expérience>.yaml
_base_: ../base.yaml          # chemin relatif à ce fichier (ou liste de chemins)
task: detection
name: yolo11n_aphids_1280
seed: 0
```

- **Fusion** : les sections (dictionnaires) sont fusionnées récursivement ; les
  listes et valeurs simples sont remplacées.
- **Surcharges** en ligne de commande, après les options :
  `uv run agridrone config -c configs/base.yaml seed=1 tracking.enabled=false`.
  Les valeurs sont lues en YAML (`1e-3` donne un float, `[1, 2]` une liste).
- **Validation stricte** : une clé inconnue (faute de frappe) fait échouer le
  chargement. Chaque tâche déclare son schéma pydantic
  (`agridrone.core.config.register_task_schema`).
- **Reproductibilité** : chaque run écrit la config résolue (`config.yaml`) et
  son empreinte SHA-256 dans `runs/<tâche>/<date>_<nom>_<hash>/`, avec l'état
  git et les versions des paquets (`environment.json`). Ces fichiers sont aussi
  attachés au run MLflow.

Arborescence prévue (créée au fil des chantiers) :

| Dossier | Contenu | Chantier |
|---|---|---|
| `base.yaml` | graine, device, chemins, MLflow | 0 |
| `data/` | sources retenues, découpages, tuilage | 2 |
| `sensors/` | définition des bandes par capteur (RVB, multispectral N bandes) | 2 |
| `detection/` | YOLO11 pucerons | 3 |
| `classification/` | classifieur maladies du blé | 4 |
| `segmentation/` | U-Net multispectral | 5 |
