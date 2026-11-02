# Notice — Planificateur de mission (v2, architecture AU1/AU2)

Module : `src\modules\planificateur\`
Dépôt : `tbouillaguet-max/Application-android-drone`, branche `claude/zen-newton-1sz0ql` (commit 69f4471).
Position dans le workflow : **premier module**. En aval : AU2 (mission par câble USB) et pipeline d'analyse (`mission_<id>.json`).

```
[PLANIFICATEUR] ──câble USB (Web Serial)──► AU2 ──► vol ──► photos + photos.csv + boite_noire.csv ──► pipeline
       └── mission_<id>.json ──► data\missions ─────────────────────────────────────────────────► pipeline
```

## 1. But
Tracer une mission sur la carte (limites, zones interdites, chemin), choisir la culture, calculer, vérifier, faire confirmer par l'opérateur, l'envoyer à AU2 avec relecture complète, puis l'archiver pour le pipeline.

## 2. Entrées
| Entrée | Format | Source |
|---|---|---|
| Saisie de l'opérateur | carte Leaflet (IGN, OSM, RPG, cadastre) | Tom |
| Fichier de mission existant (facultatif) | JSON version 1 | planificateur |
| Réponses d'AU2 | trames du protocole (MISSION_ACK, relecture, HEARTBEAT, TEXTE, ALERTE_AVARIE) | AU2 par le câble USB |
| Paramètres | `js/config.js` (caméra **provisoire**, cultures, capacités d'AU2, énergie, liaison série) | dépôt |

## 3. Sorties
| Sortie | Format | Destinataire |
|---|---|---|
| Trames de mission (MISSION_DEBUT, LIMITES, ZONE_INTERDITE, WAYPOINT, VERIFICATION, FIN) | protocole v1, 115 200 bauds | AU2 |
| `data\missions\mission_<idMission>.json` | JSON v1 + `"culture": "ble" \| "mais" \| "pommier"` ; suffixe `_2`, `_3` si l'id existe déjà avec un autre contenu (jamais d'écrasement) | **pipeline (entrée E3)** |
| `data\missions\journal_planificateur.txt` | `horodatage UTC \t NIVEAU \t mission N \t texte` (erreurs et avertissements) | Tom |

**La culture n'est jamais transmise au drone** (test automatique : trames identiques quelle que soit la culture).

## 4. Fonctionnement
1. Lancement : `lancer.bat` → `serveur_local.py` sert la page sur `http://localhost:8000` (option `--missions DOSSIER`).
2. Culture obligatoire. Un ancien fichier sans culture s'ouvre mais l'envoi reste bloqué (choix forcé) ; une culture inconnue est refusée à l'ouverture (`depuisJson`).
3. Vérifications (`verifications.js`) : culture, limites, zones, nombre de waypoints, chemin dans les limites et hors zones, altitudes, vitesses ; avertissements : marges, énergie, prises de vue, **caméra provisoire**.
4. Case « J'ai vérifié… » obligatoire, décochée à chaque modification et après chaque envoi.
5. *Connecter AU2 (câble USB)* : attente 2 s (redémarrage DTR de la Mega). *AU2 simulé* pour essayer sans carte.
6. Envoi : identifiant libre demandé au serveur ; accusé par élément, relecture octet par octet, CRC de mission.
7. Refus d'AU2 si le drone est armé ou en vol (`ETAT_INCOMPATIBLE`) ; accepté après atterrissage et désarmement automatique.
8. Succès → archivage par `serveur_local.py`, qui recontrôle version, idMission et culture.

## 5. Cohérence avec les modules voisins
- Sortie vers le pipeline (E3) : conforme à la notice du pipeline (JSON v1 + `culture`, chemin `data\missions\mission_<id>.json`). **Écart à signaler au pipeline** : avec un suffixe (`mission_12_2.json`), le pipeline doit choisir le fichier dont le contenu correspond au vol (par exemple via la date `modifieLe`).
- Liste des cultures : à garder identique dans `config.js`, `serveur_local.py` (`CULTURES`) et `pipeline\modeles.json`.

## 6. TO DO
- Paramètres de la caméra (modèle programmable à choisir) : `config.js`, puis `cameraProvisoire: false`.
- Liaison Wi-Fi (quand le module sera choisi).

## 7. Tests
`npm test` (25 tests), `python -m unittest discover -s planificateur/tests -p "test_*.py"` (6 tests), test croisé avec le banc AU2 en C++ (`BANC_AU2=127.0.0.1:5761 npm test`).
