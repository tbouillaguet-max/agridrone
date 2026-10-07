# Configs

Une expérience = un fichier YAML. Les configs de tâche héritent de `base.yaml` :

```yaml
# configs/classification/convnext_tiny.yaml
_base_: base.yaml             # chemin relatif à ce fichier (ou liste de chemins)
name: convnext_tiny
model:
  arch: convnext_tiny.fb_in22k_ft_in1k
```

`task` (ici `classification`, hérité de `classification/base.yaml`) choisit le schéma
de validation et le lanceur : `uv run agridrone train -c <config>`.

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

Arborescence :

| Dossier | Contenu | Chantier |
|---|---|---|
| `base.yaml` | graine, device, chemins, MLflow | 0 |
| `data/` | sources retenues, découpages, tuilage | 2 |
| `sensors/` | définition des bandes par capteur (RVB, multispectral N bandes) | 2 |
| `detection/` | YOLO11 pucerons (à créer : chantier reporté) | 3 |
| `classification/` | classifieur maladies du blé : `base.yaml` (données, règle de décision), `efficientnet_b0.yaml`, `convnext_tiny.yaml` | 4 |
| `segmentation/` | U-Net N bandes et baselines par indices : `base.yaml`, `unet_5bandes.yaml`, `unet_rvb.yaml` | 5 |
