# Module : `<nom-du-module>`

> Dossier : `src/modules/<nom-du-module>/` — le nom du dossier est identique à l'identifiant dans `GRAPH.md`.

## 1. Rôle
[Décrire le rôle principal en 2 phrases maximum. Que fait ce module ?]

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : [`main.py` / `serveur_local.py` / `index.html` / `ProtocoleDrone.h` / package importable…]
- **Entrées (Inputs)** :
  - [Format / Fichier / Chemin (`data/...`) / Signature d'API]
- **Sorties (Outputs)** :
  - [Format de retour / Fichier généré / Chemin (`data/...`)]

## 3. Dépendances Déclarées
- **Consomme** : [`module-A`, `module-B`] (ou `aucun`)
- **Fournit à** : [`module-C`] (ou `aucun`)
- **Données (`data/`)** : [dossiers lus / écrits]

## 4. Commandes Propres
Exécutées depuis `src/modules/<nom-du-module>/`. Indiquer les commandes réelles du module, pas une commande globale.
- **Techno** : [Python | JS | C++/Arduino | notebook]
- **Installer** : `[ex. pip install -e .[dev] | uv sync | aucune]`
- **Lint / Build** : `[ex. ruff check . | make | aucun]`
- **Tests** : `[ex. python -m pytest | npm test | make -C arduino/test_hote]`

## 5. Règle d'Isolation (Interdits)
- Ne jamais importer directement de fichiers internes d'un autre module : passer par son point d'entrée (§2) ou par ses fichiers de contrat dans `data/`.
- Ne jamais écrire en dehors de `src/modules/<nom-du-module>/` et des dossiers `data/` déclarés en §3.
- Ne jamais modifier l'état global du système depuis ce module.
