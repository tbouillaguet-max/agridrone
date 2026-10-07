# data/

Rien ici n'est versionné par git, à l'exception de ce fichier et des `.gitkeep`.

| Dossier | Contenu | Règle |
|---|---|---|
| `raw/<source>/` | archives et fichiers téléchargés tels quels, avec leur somme de contrôle | immuable : on ne modifie jamais un fichier brut |
| `interim/<source>/` | extractions, conversions de format, tuiles intermédiaires | régénérable depuis `raw/` par les scripts |
| `processed/<tâche>/` | jeux prêts à l'entraînement (YOLO, dossiers par classe, tuiles N bandes + masques) et fichiers de découpage train/val/test | régénérable depuis `raw/` + configs |

Le découpage train/val/test se fait **par source / parcelle / date**, jamais
aléatoirement par image, pour éviter les fuites entre images quasi identiques
d'une même prise de vue (chantier 2).

Les clés d'accès éventuelles (Kaggle, Roboflow) ne doivent jamais être
enregistrées dans le dépôt : variables d'environnement ou fichier `.env` (ignoré).
