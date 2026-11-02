# agridrone

Drone agricole autonome : il survole des cultures, les photographie, détecte les plantes malades ou parasitées et transmet les résultats. Ce dépôt regroupe tout ce qui touche au drone : planification de mission, protocole et électronique, analyse des images, entraînement des modèles, formation.

## Par où commencer

| Je cherche… | Je lis |
|---|---|
| les modules, leurs dépendances, où sont les données | [`GRAPH.md`](GRAPH.md) |
| ce que fait un module et comment le lancer | `src/modules/<module>/README.md` |
| les formats de fichiers échangés entre modules | [`docs/contrats.md`](docs/contrats.md) |
| les règles de travail (pour Claude et pour moi) | [`CLAUDE.md`](CLAUDE.md) |
| l'architecture matérielle AU1 / AU2, le câblage, les essais en vol | [`docs/`](docs/) |

## Structure

```
CLAUDE.md  GRAPH.md  README.md
.claude/templates/MODULE_README.md   modèle de README de module
docs/                  architecture, câblage, essais en vol, contrats, notices historiques (docs/notices/)
src/modules/           un dossier par module (voir GRAPH.md)
tools/verifier_graph.py   cohérence GRAPH.md ↔ dossiers ↔ README
data/                  données, missions, vols, runs, datasets : hors Git (DRONE_DATA_DIR)
_archive/              reliquats locaux de la migration, ignorés par Git
```

## Démarrage

Chaque module a ses propres commandes (§ 4 de son README) : le dépôt mélange JavaScript, Python et C++/Arduino. Exemples :

```bash
python tools/verifier_graph.py                                  # cohérence du dépôt
cd src/modules/planificateur && npm test                        # tests JS du planificateur
cd src/modules/protocole && make -C arduino/test_hote           # tests C++ du protocole
cd src/modules/pipeline-analyse && python -m pytest tests       # tests du pipeline
```

## Ajouter un module

Voir `CLAUDE.md` § 9 : dossier dans `src/modules/`, README au format du template, ligne et nœud dans `GRAPH.md`, vérification par `tools/verifier_graph.py`.
