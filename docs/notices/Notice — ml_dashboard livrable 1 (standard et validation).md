# Notice — ml\_dashboard, livrable 1

Oct 29, 2026 · @Tom

## But

Le livrable 1 répond à une seule question : **ce dossier de run est-il lisible par le dashboard ?** Il fixe le format commun de tous les entraînements (`schema_version: 1`) et fournit l'outil qui le vérifie.

Il ne lance aucun entraînement et ne modifie aucun fichier : il **lit** un dossier et **rend un diagnostic**. Les livrables suivants s'appuient dessus :

- le RunLogger et les adaptateurs (livrables 2 et 3) **écrivent** des dossiers conformes ;
- l'import Kaggle (livrable 4) **valide** chaque run avant de le ranger dans `runs\` ;
- le dashboard (livrable 5) **lit** les fichiers en s'appuyant sur les mêmes constantes.

La vérification attrape une erreur au moment où le run est produit, plutôt qu'au moment où un graphique du dashboard sort faux ou vide.

## Vue d'ensemble

Cinq fichiers de code et quatre schémas JSON, avec un seul point d'entrée, `validate_run`.

&#91;embedded content: architecture du livrable 1 · 5 fichiers de code, 4 schémas\]

`validate.py` fait le travail. `standard.py` et `schemas/*.json` portent les règles. `cli.py` n'est qu'une couche d'affichage autour de `validate_run`, que tu peux aussi appeler depuis un notebook.

## Entrées

L'unique entrée est un **chemin de dossier**. Tout le reste est lu à l'intérieur de ce dossier, sans réseau ni configuration.

**Le chemin donné** peut être de trois niveaux. `find_runs` repère tout dossier contenant un `meta.json` :

| Chemin donné | Exemple | Runs validés |
| --- | --- | --- |
| un run | `runs\plantes\20261029_180500_effnet-b0` | ce run |
| un dossier de projet | `runs\plantes` | tous les runs du projet |
| le dossier central | `runs` | tous les runs de tous les projets |

**Les fichiers lus dans chaque run** (formats détaillés dans `STANDARD.md`) :

| Fichier | Lu comme | Toujours requis ? |
| --- | --- | --- |
| `meta.json` | JSON | oui |
| `config.yaml` | YAML | oui |
| `classes.json` | JSON | oui |
| `epochs.csv` | CSV | oui |
| `predictions/val.csv`, `test.csv` | CSV | `val.csv` si classification terminée |
| `detection/metrics.json`, `pr_curves.csv` | JSON, CSV | `metrics.json` si détection terminée |
| `artifacts/manifest.json` + fichiers | JSON + images/HTML | manifest dès qu'il y a un fichier |
| `extra_results/*.csv` | CSV | non |
| `model/` | contenu seulement compté | non (alerte si vide) |

Tous les fichiers sont lus en **UTF-8**, et les CSV en texte brut (`dtype=str`) : une classe nommée `1` reste la chaîne `"1"`, et chaque conversion en nombre est contrôlée.

**Les options de la ligne de commande** :

| Option | Effet |
| --- | --- |
| `paths` (un ou plusieurs) | dossiers à valider |
| `--quiet` / `-q` | n'affiche que les runs ayant au moins un problème |
| `--strict` | les alertes font aussi échouer la commande |
| `--json` | sortie JSON au lieu du texte |
| `--version` | version du module et du standard |

## Sorties

Chaque run produit un **rapport** (`ValidationReport`) qui liste ses problèmes (`Issue`). Rien n'est écrit sur disque.

**Une `Issue`** a trois champs :

| Champ | Valeurs | Sens |
| --- | --- | --- |
| `level` | `error` ou `warning` | erreur = le dashboard lira mal le run ; alerte = lisible mais incomplet ou suspect |
| `file` | chemin relatif au run | où se trouve le problème (`.` = le dossier lui-même) |
| `message` | texte en français | quoi corriger, avec la valeur fautive |

**Un `ValidationReport`** expose :

- `run_dir` : le dossier validé (chemin absolu) ;
- `issues`, `errors`, `warnings` : toutes les issues, ou filtrées par niveau ;
- `ok` : vrai s'il n'y a **aucune erreur** (les alertes sont tolérées) ;
- `schema_version` : la version lue dans `meta.json` ;
- `format()` : le texte affiché dans la console ;
- `to_dict()` : la même chose en dictionnaire, pour `--json`.

**Affichage console** (en ASCII, pour éviter les problèmes d'encodage de la console Windows) :

```
[ECHEC] C:\...\runs\plantes\20261029_180500_effnet-b0  (1 erreur(s), 1 alerte(s))
    ERREUR  predictions/val.csv : 3 ligne(s) dont les probabilités ne somment pas à 1 (label_mode 'single')
    ALERTE  model : aucun checkpoint enregistré

0/1 run(s) valide(s)
```

**Code de sortie** de la commande, exploitable dans un script :

| Code | Signification |
| --- | --- |
| `0` | tous les runs sont valides |
| `1` | au moins un run a une erreur (ou une alerte, avec `--strict`) |
| `2` | aucun run trouvé sous le chemin donné |

## Fonctionnement

La commande trouve les runs, puis valide chacun **indépendamment** : un run cassé n'empêche pas de contrôler les autres.

**Côté commande** (`cli.py`) :

1. Lire les arguments ; régler la console pour qu'un caractère impossible à afficher soit remplacé au lieu de faire planter le programme.
2. Pour chaque chemin, appeler `find_runs` qui liste les dossiers contenant un `meta.json`.
3. Appeler `validate_run` sur chaque run trouvé.
4. Afficher les rapports (texte ou JSON), puis renvoyer le code de sortie.

**Côté validation** (`validate_run` dans `validate.py`), dans cet ordre :

1. **Dossier** : s'il n'existe pas, une erreur et c'est terminé.
2. **`meta.json` d'abord**, car il commande tout le reste. On en extrait la `task` (classification, détection ou segmentation) et le `status` (running, completed…). Si `schema_version` est inconnue, la validation **s'arrête** : le code ne sait pas lire ce format.
3. **Éléments inattendus** à la racine du run : alertes.
4. **`config.yaml`** : YAML lisible et dictionnaire à la racine.
5. **`classes.json`** : on en extrait la liste des classes et le `label_mode` (single ou multi). Ces deux informations servent aux contrôles des prédictions et de la détection.
6. **`epochs.csv`** : colonnes, noms, types, ordre des époques.
7. **`predictions/`** : vérifié seulement pour la classification. Le contrôle des probabilités dépend du `label_mode`.
8. **`detection/`** : vérifié seulement pour la détection et la segmentation.
9. **`artifacts/`** et **`extra_results/`** : manifests et fichiers référencés.
10. **`model/`** : présence d'un checkpoint si le run est terminé.

**Trois idées guident ce déroulé :**

- **Le contexte d'abord.** La `task`, le `status` et les classes changent les règles. Par exemple, `val.csv` n'est obligatoire que pour une classification au statut `completed`, et `test.csv` est interdit tant que le run tourne.
- **On continue malgré une erreur.** Chaque contrôle ajoute ses problèmes au rapport et rend la main. Tu vois donc toutes les erreurs du run d'un coup, pas seulement la première.
- **Une règle = un endroit.** Les noms de fichiers et les motifs viennent de `standard.py` ; les formats JSON viennent de `schemas/`. Le validateur n'invente aucune règle.

## Règles vérifiées

Une **erreur** signale ce qui fausserait ou bloquerait le dashboard ; une **alerte** signale ce qui est incomplet ou suspect.

| Fichier | Erreurs | Alertes |
| --- | --- | --- |
| `meta.json` | absent ou JSON invalide ; clé manquante ou inconnue ; mauvais type (un booléen n'est pas un entier) ; `task` ou `status` hors liste ; date non ISO ; `schema_version` non prise en charge ; `run_id` différent du nom du dossier | `project` différent du dossier parent ; run terminé sans `ended_at` ou `duration_s` |
| `config.yaml` | absent ; YAML invalide ; pas un dictionnaire à la racine | fichier vide |
| `classes.json` | absent ; classe en double ou nom interdit (virgule, `\|`, espace en bord) ; moins de 2 classes en mono-label ; `positive_class` absente des classes, hors binaire, ou utilisée en multi-label ; `multi` pour une détection | binaire sans `positive_class` (le dashboard prendra la 2e classe) |
| `epochs.csv` | absent ; colonne obligatoire manquante ; nom hors motif `train_*` / `val_*` ; valeur non numérique ; `epoch` non entier ou non strictement croissant ; `lr` négatif ; aucune ligne pour un run terminé | `val_loss` entièrement vide |
| `predictions/*.csv` | fichier autre que `val.csv` / `test.csv` ; `val.csv` absent pour un run terminé ; `test.csv` présent alors que le run tourne ; colonne ou `proba_*` manquante ; `proba_*` d'une classe inconnue ; `id` vide ou en double ; classe inconnue dans `y_true` / `y_pred` ; probabilité vide ou hors \[0, 1\] ; en mono-label, probabilités dont la somme s'écarte de 1 de plus de 0,001 ; en multi-label, classe répétée dans une cellule | colonnes supplémentaires ; `y_pred` différent de la classe de proba maximale (mono) ou du seuil 0,5 (multi) |
| `detection/` | `metrics.json` absent pour un run terminé ; schéma non respecté (dont métrique hors \[0, 1\], par exemple `55` au lieu de `0.55`) ; classe inconnue ; `pr_curves.csv` sans `class`, `recall`, `precision` ou valeurs hors \[0, 1\] | segmentation sans métriques `mask` ; dossier présent pour une classification |
| `artifacts/` | fichiers sans `manifest.json` ; manifest invalide ; fichier référencé absent ; chemin qui sort du dossier (`../`) | fichier non décrit dans le manifest ; extension non affichable |
| `extra_results/` | manifest invalide ou fichier référencé absent (le manifest est facultatif) | fichier autre que `.csv` |
| `model/` | — | vide pour un run terminé |
| racine du run | — | élément non prévu par le standard |

Pourquoi `y_pred` ne donne qu'une alerte : tu as le droit d'enregistrer une prédiction faite avec un seuil réglé. Le dashboard recalcule de toute façon les prédictions à partir des probabilités.

## Référence des fonctions

Les fonctions utilisables depuis ton propre code, module par module. Les fonctions qui commencent par `_` sont internes.

**`standard.py`** : constantes et petites fonctions de nommage.

| Fonction / constante | Entrée → sortie | Exemple |
| --- | --- | --- |
| `SCHEMA_VERSION`, `SUPPORTED_SCHEMA_VERSIONS` | constantes | `1`, `(1,)` |
| `TASKS`, `STATUSES`, `SPLITS`, `LABEL_MODES` | listes des valeurs autorisées | `("single", "multi")` |
| `slugify(texte)` | texte libre → identifiant valide | `"EfficientNet B0"` → `"efficientnet-b0"` |
| `make_run_id(nom, date?)` | nom court → `run_id` daté | → `"20261029_180500_effnet-b0"` |
| `proba_column(classe)` | classe → nom de colonne | `"mildiou"` → `"proba_mildiou"` |
| `per_class_column(split, metrique, classe)` | → colonne d'`epochs.csv` | → `"val_recall__mildiou"` |
| `split_metric_column(colonne)` | colonne → (split, métrique, classe ou None) | `"val_recall__mildiou"` → `("val", "recall", "mildiou")` |
| `split_labels(cellule)`, `join_labels(liste)` | décode / encode une cellule multi-label | `"mildiou\|insectes"` ↔ `["mildiou", "insectes"]` |

**`schema_lite.py`** : vérifie un JSON contre un schéma.

| Fonction | Entrée → sortie |
| --- | --- |
| `load_schema(nom)` | `"meta"`, `"classes"`, `"manifest"` ou `"detection_metrics"` → schéma (dictionnaire), mis en cache |
| `validate_instance(donnée, schéma)` | → liste de messages d'erreur (vide = conforme) |

Ce petit validateur remplace la librairie `jsonschema` pour ne pas ajouter de dépendance. Il ne gère que les mots-clés utilisés par nos 4 schémas. Les schémas restent des JSON Schema standards, lisibles par d'autres outils.

**`validate.py`** : le validateur de run.

| Fonction / classe | Entrée → sortie |
| --- | --- |
| `validate_run(dossier)` | chemin d'un run → `ValidationReport` |
| `find_runs(racine)` | run, projet ou dossier central → liste des dossiers de run |
| `ValidationReport`, `Issue` | voir la section Sorties |

**`cli.py`** et **`__main__.py`** : la commande `python -m ml_dashboard`. `main(argv)` renvoie le code de sortie, ce qui permet aussi de l'appeler depuis Python.

Utilisation depuis un notebook :

```python
from ml_dashboard import validate_run

report = validate_run(r"data\runs\plantes\20261029_180500_effnet-b0")
print(report.format())
if not report.ok:
    raise RuntimeError("Run non conforme")
```

## Faire évoluer le standard et tester

Toute modification du format, même l'ajout d'une colonne, passe par une **nouvelle version** : les anciens runs doivent rester lisibles.

1. Modifier la règle à sa place : `standard.py` pour les noms et motifs, `schemas/*.json` pour les formats JSON, la fonction `_check_…` concernée pour une règle de cohérence.
2. Passer `SCHEMA_VERSION` à 2 et l'ajouter à `SUPPORTED_SCHEMA_VERSIONS`.
3. Ajouter dans `STANDARD.md` une section « Changements depuis la version 1 ».
4. Faire relire les runs v1 au code (conversion à la lecture) sans jamais les réécrire sur disque.
5. Ajouter un test pour la nouvelle règle.

**Les tests** (`tests/`, 45 au total) partent d'un run valide puis le cassent d'**une seule façon** pour vérifier que la bonne erreur est détectée :

- `conftest.py` fabrique des runs valides à la main : classification binaire, multi-classes et multi-label, détection, segmentation, run en cours ;
- `test_validate.py` contient un test par règle, plus les tests de `find_runs` et de la commande (codes de sortie, sortie JSON) ;
- les exemples écrits dans les docstrings de `standard.py` sont aussi exécutés comme tests.

Pour les lancer : `python -m pytest` depuis `src\modules\ml-dashboard`.
