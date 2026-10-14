# Projet olivier

Le drone survole des oliveraies pour repérer les maladies et les ravageurs. Ce dossier
regroupe tout ce qui est propre à l'olivier ; le code commun, l'installation et le
téléchargement des données sont décrits dans le [README du dépôt](../README.md).

## Contenu

```
olivier/
  configs/
    base.yaml               hérite de configs/base.yaml ; données data/olivier/, runs runs/olivier/
    data/                   registre des sources (sources.yaml), empreintes (sources.lock.yaml),
                            listes de fichiers des gros dépôts Mendeley (manifests/)
  reports/
    data_inventory.md       inventaire des données publiques (12 octobre 2026)
  tp/                       travaux pratiques : maladies des feuilles, mouche de l'olive
  LICENCES_DONNEES.txt      statut, licence et attribution de chaque source de l'olivier
```

Données : `data/olivier/` (raw, interim, processed). Runs : `runs/olivier/`.

## Étapes

| Étape | Contenu | Commande | État |
|---|---|---|---|
| Inventaire | Données publiques : drone multispectral, Xylella, feuilles, ravageurs, fruits ; 43 sources au registre (33 téléchargeables, 7 à récupérer à la main, 3 écartées) | [reports/data_inventory.md](reports/data_inventory.md) | fait |
| Téléchargement | Tout ce qui est téléchargeable, vérifié et extrait (environ 137 Go d'archives) | `uv run agridrone data download --project olivier` | commande prête et testée |
| TP | Reconnaître les maladies des feuilles (œil de paon, acariose) et compter la mouche de l'olive dans les pièges | `uv run jupyter lab olivier/tp/` ; [tp/README.md](tp/README.md) | fait (notebooks élève et corrigés, résultats de référence) |
| Modèles du projet | Segmentation des houppiers par drone, état sanitaire par arbre (ICAERUS), feuilles, mouche de l'olive : recommandations de l'inventaire (§ 10) | — | à faire |

Depuis la racine du dépôt :

```bash
uv run agridrone data list --project olivier        # statut, licence, taille
uv run agridrone data download --project olivier    # tout ce qui est téléchargeable
uv run agridrone data verify --project olivier      # sommes de contrôle
uv run agridrone data licences --project olivier    # régénère LICENCES_DONNEES.txt
```

Pour les TP, six jeux suffisent (environ 3,5 Go) : voir [tp/README.md](tp/README.md).

## Licences des données

Statut, licence, conditions et attribution de chaque source :
[`LICENCES_DONNEES.txt`](LICENCES_DONNEES.txt). Vérifications détaillées et jeux
écartés : [reports/data_inventory.md](reports/data_inventory.md).
