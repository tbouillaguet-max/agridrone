# data/

Rien ici n'est versionné par Git, à l'exception de ce fichier. Racine configurable par la variable d'environnement `DRONE_DATA_DIR`. Tableau complet (qui produit, qui lit, taille) : « Données » dans [`GRAPH.md`](../GRAPH.md).

```
missions/                 missions archivées par le planificateur (mission_<id>.json)
vols/entrant/<vol>/       vols reçus : images/, photos.csv, boite_noire.csv
vols/<date>_<id>/         résultats d'analyse du pipeline (rapport.html…)
runs/<projet>/<run_id>/   runs d'entraînement au standard ml-dashboard
datasets/pommier/         raw/ (immuable), archives/
datasets/mais/            raw/, curated/, labels/
models/                   modèles ONNX exportés (à venir)
```

Les dossiers vides sont recréés avec `mkdir -p`. Ne jamais déposer de clé (Kaggle, Roboflow) ici.
