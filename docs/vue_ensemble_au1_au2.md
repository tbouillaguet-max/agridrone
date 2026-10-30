# AgriDrone — planificateur de mission, protocole commun et journal de vol

Drone agricole (châssis Phantom 3 Standard) qui photographie une parcelle
selon une mission préparée au bureau, puis rapporte ses photos pour qu'un
pipeline d'apprentissage automatique y repère les plantes malades.
L'électronique de vol est faite de **deux Arduino Mega** :

* **AU1** — pilotage et stabilisation (IMU, moteurs, failsafes) ;
* **AU2** — navigation et capteurs (GPS, magnétomètre, mission, LoRa, carte
  SD, déclenchement de la caméra).

```
 PC (Chrome)                  câble USB     AU2 (Mega)          Serial1     AU1 (Mega)
 ┌──────────────────────────┐  (au sol)    ┌───────────────────┐ ────────▶ ┌──────────────┐
 │ planificateur web :      │ ───────────▶ │ mission, GPS,     │ ◀──────── │ pilotage,    │
 │ carte IGN, culture,      │ ◀─────────── │ magnétomètre,     │  115200   │ stabilisation│
 │ limites, zones,          │ trames AA 55 │ caméra, carte SD  │           │ moteurs      │
 │ quadrillage, calculs,    │              │ (photos.csv,      │           └──────────────┘
 │ vérifications, archivage │              │  boîte noire)     │
 └────────────┬─────────────┘              └──┬─────────┬──────┘
              │ mission_<id>.json              │ LoRa    │ Wi-Fi après l'atterrissage
              ▼                                ▼         ▼ (module à choisir)
   data\missions ─────────────▶ boîtier sol   data\vols\entrant ──▶ pipeline d'analyse ──▶ rapport.html
```

* **Au sol, avant le vol** : la mission (avec la **culture** de la parcelle)
  est tracée dans le planificateur, vérifiée, **confirmée par l'opérateur**
  (case à cocher), puis envoyée à AU2 par le **câble USB** et **relue
  entièrement**. Le fichier est archivé dans `data\missions`. La culture
  n'est pas transmise au drone : elle sert au pipeline d'analyse.
* **En vol** : AU2 déclenche la caméra et écrit `photos.csv` ; toute alerte,
  erreur ou ordre reçu est écrit dans `boite_noire.csv` sur sa carte SD. La
  seule liaison avec le sol est la LoRa d'AU2 (position, alertes ; ordres
  atterrissage, retour, **arrêt d'urgence**). Aucun réseau mobile.
* **Après l'atterrissage** : le drone se désarme seul ; une nouvelle mission
  peut être chargée. Photos et journaux partent au PC en Wi-Fi (module à
  choisir) pour le pipeline d'analyse.

## Ce que contient le dépôt

| Dossier | Contenu | Point d'entrée |
|---|---|---|
| [`protocole/`](../src/modules/protocole/) | **Spécification du protocole commun** et des fichiers de vol, en-têtes C++ pour Arduino (`ProtocoleDrone.h`, `FichiersVol.h`), vecteurs de test, croquis d'exemple, banc d'essai AU2 exécutable sur PC, contrôle des fichiers d'un vol | [`SPECIFICATION.md`](../src/modules/protocole/SPECIFICATION.md) |
| [`planificateur/`](../src/modules/planificateur/) | **Planificateur de mission** : page web pour Chrome, serveur local qui archive les missions | [`planificateur/README.md`](../src/modules/planificateur/GUIDE.md) |
| [`docs/`](.) | Architecture, câblage, planificateur, tests, essais en vol | ci-dessous |
| [`tp/`](../src/modules/formation-tp/) | **TP** : fiches et exercices web (planificateur), étapes Arduino à venir | [`tp/README.md`](../src/modules/formation-tp/GUIDE.md) |

## Documentation

| Document | Pour… |
|---|---|
| [Architecture](architecture.md) | comprendre les composants, les échanges, la sécurité (confirmation, arrêt d'urgence, boîte noire) |
| [Câblage](cablage.md) | relier le PC à AU2, AU2 à AU1, la carte SD |
| [Planificateur](planificateur.md) | servir la page en local, préparer, envoyer et archiver une mission |
| [Tests](tests.md) | toutes les commandes de test et les essais de bout en bout sans drone |
| [Essais en vol](essais_en_vol.md) | progression des essais avec le vrai drone, listes de contrôle |
| [Spécification du protocole](../src/modules/protocole/SPECIFICATION.md) | trames, messages, cycle de vie, arrêt d'urgence, fichiers `photos.csv` et `boite_noire.csv` |

## Démarrage rapide (sans drone)

1. **Planificateur** : `planificateur/lancer.bat` (Windows) ou
   `./planificateur/lancer.sh`.
2. *Ouvrir…* `exemples/mission_exemple.json`, vérifier la **culture**,
   cliquer **AU2 simulé**, cocher « J'ai vérifié… », **Envoyer la mission** :
   elle est chargée et relue dans l'AU2 simulé, puis archivée dans
   `data\missions`.
3. Avec la vraie carte : téléverser `protocole/arduino/exemples/banc_au2_mission`
   dans la Mega, la brancher en USB, puis **Connecter AU2 (câble USB)**.

## Tests automatiques

```bash
cd planificateur && npm test                                             # JavaScript (Node ≥ 20)
python -m unittest discover -s planificateur/tests -p "test_*.py"        # archivage (serveur_local.py)
make -C protocole/arduino/test_hote                                      # C++ (protocole + fichiers de vol)
cd tp/exercices_web && npm run test:corrections                          # corrections du TP (web)
python protocole/outils/verifier_fichiers_vol.py protocole/exemples_fichiers/vol_exemple
```

Détail, essais de bout en bout et banc d'essai C++ : [docs/tests.md](tests.md).

## Matériel

| Élément | Référence |
|---|---|
| Châssis, moteurs, batterie | Phantom 3 Standard (électronique DJI remplacée) |
| AU1, AU2 | 2 × Arduino Mega 2560 |
| Carte SD | lecteur SD SPI relié à AU2 |
| Caméra | **TO DO** : caméra programmable, modèle à choisir (déclenchée par AU2, nom de fichier imposé) |
| Liaison sol | LoRa (un module, sur AU2) |
| Transfert des photos | **TO DO** : module Wi-Fi à choisir |
| PC | Windows 10/11, macOS ou Linux, Chrome ou Edge, Python 3, Node.js 20+ |
