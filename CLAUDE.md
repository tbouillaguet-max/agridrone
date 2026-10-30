# CLAUDE.md — monorepo `drone`

Drone agricole autonome : planifier une mission, survoler les cultures, photographier, analyser, transmettre. Le dépôt regroupe tout ce qui touche au drone, de près ou de loin (logiciel, électronique, ML, outils de production).

## 1. Architecture & lecture minimale de contexte
- Le projet est découpé en modules indépendants dans `src/modules/<module>/`.
- `GRAPH.md` à la racine est la SEULE source de vérité des dépendances et des emplacements de données. Lis-le AVANT toute tâche impliquant plusieurs modules.
- Chaque module possède son `README.md` (`src/modules/<module>/README.md`), au format de `.claude/templates/MODULE_README.md`.
- RÈGLE D'OR : pour comprendre un module, lis UNIQUEMENT son `README.md`. Ne lis pas le code d'un module tiers s'il n'est pas directement impacté par la tâche.
- Les contrats de fichiers entre modules (formats, colonnes, chemins) sont dans `docs/contrats.md`.

## 2. Règle des 3 frontières
- **TOUJOURS** : mettre à jour le `README.md` d'un module ET sa ligne/nœud dans `GRAPH.md` dès que ses entrées, sorties ou dépendances changent.
- **DEMANDER D'ABORD** : modifier un fichier appartenant à un autre module que celui désigné par la tâche.
- **JAMAIS** : supprimer un module sans demande explicite de Tom, modifier les tests d'un module tiers sans accord, éditer la structure de `GRAPH.md` sans modifier le README du module correspondant.

### Dérogations accordées par Tom (30 octobre 2026)
Valables pour le rôle d'architecte et les opérations d'architecture que Tom demande (migration, refactoring, ajout ou retrait de module) :
- une opération d'architecture peut toucher plusieurs modules (dérogation à « une tâche = un module » et à « demander d'abord ») ;
- l'architecte peut lire le code d'un module tiers pour auditer ses contrats ;
- un module peut être supprimé ou fusionné si Tom l'a demandé, avec mise à jour de `GRAPH.md` dans le même commit.
Pour une tâche ordinaire sur un module, les règles ci-dessus s'appliquent sans dérogation.

## 3. Discipline de jetons & outils
- Utilise `Grep` ou `Glob` pour cibler les fichiers nécessaires. Ne charge jamais des dossiers entiers.
- Ne ré-affiche pas le contenu d'un fichier lu : indique `path/to/file` et les numéros de ligne.
- Ne génère pas de code de démonstration non demandé. Donne directement les diffs ou modifications ciblées.
- Une tâche = un module. Si une demande touche plusieurs modules, propose d'abord un plan de découpage et traite-les séquentiellement (sauf opération d'architecture, § 2).

## 4. Maintenance de GRAPH.md
Quand tu ajoutes, modifies ou supprimes un module :
1. Mets à jour le tableau Markdown dans `GRAPH.md`.
2. Mets à jour le bloc `mermaid` correspondant.
3. Les identifiants Mermaid correspondent exactement aux noms des dossiers des modules.
4. Vérifie : `python tools/verifier_graph.py` (tableau ↔ dossiers ↔ Mermaid ↔ README).

## 5. Routage des modèles
- Tâches simples (recherche de code, vérification de syntaxe, lecture de structure, formatage) : subagent `haiku`.
- Agent principal (Sonnet/Opus) : architecture, refactoring complexe, bugs multi-modules.

## 6. Commandes (le dépôt est polyglotte : pas de commande globale)
- Chaque module déclare ses commandes réelles dans le § 4 de son README (Python : `python -m pytest`, `uv run pytest` ; JS : `npm test` ; C++/Arduino : `make`).
- Exécute-les depuis `src/modules/<module>/`. Ne suppose jamais `pnpm`, `npm run … --filter` ou un gestionnaire de paquets unique pour tout le dépôt.
- Le seul outil transverse est `python tools/verifier_graph.py` (Python ≥ 3.10, sans dépendance).

## 7. Données
- `data/` n'est jamais versionné (sauf `README.md` et `.gitkeep`). Emplacements et tailles : tableau « Données » de `GRAPH.md`.
- Racine des données : variable d'environnement `DRONE_DATA_DIR`, sinon `<racine du dépôt>/data`. Les modules ne codent jamais de chemin absolu.
- Les modèles (`*.onnx`, `*.pt`), les photos de vol, les datasets et les runs restent hors Git.

## 8. Contrats à ne pas casser sans prévenir
- `photos.csv` et `boite_noire.csv` (colonnes exactes) : produits par AU2, lus par `pipeline-analyse`. Source : `src/modules/protocole/SPECIFICATION.md` § 12.
- `mission_<id>.json` (JSON v1, champ `culture`) : produit par `planificateur`, lu par `pipeline-analyse`.
- Liste des cultures (`ble`, `mais`, `pommier`) : identique dans `planificateur/js/config.js`, `planificateur/serveur_local.py` (`CULTURES`), `pipeline-analyse/modeles.json` et `pipeline-analyse/analyse/contrat.py`. Toute modification touche les quatre, plus `docs/contrats.md`.

## 9. Créer un nouveau module
1. Crée `src/modules/<nom>/` (minuscules, tirets, sans espace) avec son point d'entrée.
2. Copie `.claude/templates/MODULE_README.md` en `README.md` et remplis les 5 sections.
3. Ajoute une ligne au tableau de `GRAPH.md`, le nœud et ses arêtes dans le bloc Mermaid, et ses dossiers dans le tableau « Données ».
4. Si le module échange des fichiers avec un autre : décris le format dans `docs/contrats.md`.
5. Lance `python tools/verifier_graph.py`, puis les tests du module.
6. Module hors drone (autre projet de Tom) : il n'a rien à faire ici.
