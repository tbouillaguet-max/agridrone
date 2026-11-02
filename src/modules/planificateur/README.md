# Module : `planificateur`

> Dossier : `src/modules/planificateur/`. Guide d'usage détaillé : [`GUIDE.md`](GUIDE.md). Notice historique : `docs/notices/notice_planificateur.md`.

## 1. Rôle
Planificateur de mission du drone : trace limites, zones interdites et chemin sur une carte, vérifie, fait confirmer l'opérateur, envoie la mission à AU2 par câble USB (Web Serial) puis l'archive pour le pipeline. Premier maillon du workflow.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `serveur_local.py` (sert `index.html` sur `http://localhost:8000`) ; lancement par `lancer.bat` / `lancer.sh`.
- **Entrées** :
  - saisie de l'opérateur sur la carte (Leaflet : IGN, OSM, RPG, cadastre) ;
  - fichier de mission JSON v1 existant (facultatif) ;
  - réponses d'AU2 (MISSION_ACK, relecture, HEARTBEAT, TEXTE, ALERTE_AVARIE) ;
  - paramètres dans `js/config.js` (caméra provisoire, cultures, capacités d'AU2).
- **Sorties** :
  - trames de mission du protocole v1 vers AU2 (115 200 bauds) ;
  - `data/missions/mission_<id>.json` (JSON v1 + `culture`) ;
  - `data/missions/journal_planificateur.txt`.
- La culture n'est jamais transmise au drone (test automatique).

## 3. Dépendances Déclarées
- **Consomme** : `protocole` (trames, vecteurs de test `protocole/vecteurs_test.json`, banc AU2 pour le test croisé)
- **Fournit à** : `pipeline-analyse` (missions), `formation-tp`
- **Données (`data/`)** : écrit `data/missions/`

## 4. Commandes Propres
Depuis `src/modules/planificateur/`.
- **Techno** : JS (page web, sans dépendance) + Python (serveur local)
- **Installer** : aucune dépendance
- **Lancer** : `lancer.bat` ou `python serveur_local.py [port] [--missions DOSSIER]`
- **Tests** : `npm test` (JS) et `python -m unittest discover -s tests -p "test_*.py"` (Python) ; test croisé avec le banc AU2 : `BANC_AU2=127.0.0.1:5761 npm test`

## 5. Règle d'Isolation (Interdits)
- La liste des cultures reste identique à `serveur_local.py` (`CULTURES`), `pipeline-analyse/modeles.json` et `pipeline-analyse/analyse/contrat.py` (voir `docs/contrats.md`).
- Ne jamais écraser une mission archivée (suffixes `_2`, `_3`).
- Ne jamais envoyer à AU2 sans confirmation de l'opérateur ; ne jamais importer le code interne d'un autre module.
