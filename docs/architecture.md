# Architecture

Ce document décrit les composants, leurs échanges, la sécurité, la robustesse,
et justifie le choix de chaque bibliothèque. Le format exact des messages et
des fichiers est dans [protocole/SPECIFICATION.md](../src/modules/protocole/SPECIFICATION.md).

## 1. Vue d'ensemble

| Composant | Matériel | Rôle | Code |
|---|---|---|---|
| Planificateur | PC, Chrome | tracer le terrain, choisir la culture, générer le chemin, calculer, vérifier, faire confirmer, envoyer à AU2 par le câble USB, archiver | `planificateur/` |
| Serveur local | PC, Python | servir la page sur `localhost`, archiver les missions dans `data\missions`, écrire le journal du planificateur | `planificateur/serveur_local.py` |
| AU2 | Arduino Mega | navigation : GPS, magnétomètre, mission, caméra, carte SD (`photos.csv`, boîte noire), LoRa, relais des ordres vers AU1 | autre dépôt ; exemples dans `protocole/arduino/exemples/` |
| AU1 | Arduino Mega | pilotage : IMU, stabilisation, moteurs, failsafes, désarmement automatique, arrêt d'urgence | autre dépôt |
| En-têtes C++ | AU1, AU2, Uno, boîtier sol | protocole (structures, CRC, décodeur, double confirmation de l'arrêt) ; lignes des fichiers de la carte SD | `protocole/arduino/ProtocoleDrone/` |
| Banc AU2 | PC (g++) ou Mega | AU2 minimal : réception de mission, refus si armé, arrêt d'urgence | `protocole/arduino/exemples/banc_au2_mission/` |
| Pipeline d'analyse | PC | détecter les plantes malades sur les photos, rapport HTML | `src\modules\pipeline-analyse` (autre dépôt) |

Le **même format de trame** (`AA 55 | version | type | séquence | longueur | données | CRC16`)
circule sur le câble USB (PC ↔ AU2), sur la liaison série AU2 ↔ AU1 et sur la LoRa.

## 2. Place dans le flux de travail

```
 Planificateur ──(câble USB, au sol)──▶ AU2 ◀──série──▶ AU1
   │ mission_<id>.json (avec la culture)       │ vol : photos, photos.csv, boite_noire.csv
   ▼                                           ▼ Wi-Fi après l'atterrissage (TO DO)
 data\missions ────────────────▶ Pipeline d'analyse ◀── data\vols\entrant\<vol>
                                               │
                                               ▼ rapport.html (carte des zones malades)
```

| Ce module… | reçoit de… | et produit pour… |
|---|---|---|
| Planificateur | l'opérateur | AU2 (trames de mission), le pipeline (`mission_<id>.json` avec `culture`) |
| AU2 | le planificateur (mission), AU1 (alertes, télémétrie), le sol (ordres) | AU1 (consignes, arrêt), le sol (alertes), le pipeline (`photos.csv`, `boite_noire.csv`) |
| Pipeline | AU2 (photos, journaux), le planificateur (mission archivée), l'entraînement (modèles ONNX) | le rapport |

Chaque module **vérifie que ses entrées correspondent aux sorties du module
précédent** et nomme le module fautif en cas d'écart :

* AU2 refuse une mission incohérente (`MISSION_ACK` avec un statut d'erreur) ;
* `serveur_local.py` refuse d'archiver une mission sans culture valide ou dont
  l'identifiant ne correspond pas ;
* `protocole/outils/verifier_fichiers_vol.py` contrôle `photos.csv` et
  `boite_noire.csv` (colonnes, formats, photos présentes) contre le contrat ;
* le pipeline refait ce contrôle avant toute analyse.

## 3. Les échanges, dans l'ordre d'une journée de travail

### 3.1 Préparation (au bureau ou au bord du champ)

```
Planificateur                                              AU2
 tracé, culture, quadrillage, calculs, vérifications
 case « J'ai vérifié la mission » cochée par l'opérateur
 ─ USB : MISSION_DEBUT, LIMITES, ZONES, WAYPOINTS ─────────▶ stocke, MISSION_ACK pour chaque élément
                                                             (ETAT_INCOMPATIBLE si armé ou en vol)
 ─ MISSION_VERIFICATION (relecture complète) ──────────────▶ renvoie chaque élément, comparé octet par octet
 ─ MISSION_FIN (CRC de mission) ───────────────────────────▶ valide (CRC), drapeau « mission chargée »
 archivage : data\missions\mission_<id>.json
```

### 3.2 Vol

```
AU2 ── HEARTBEAT (500 ms), consignes ──────────────▶ AU1
AU2 ◀── HEARTBEAT (500 ms), TELEMETRIE, ALERTE_AVARIE ── AU1
AU2 : déclenche la caméra (nom de fichier imposé), écrit photos.csv
AU2 : écrit chaque alerte, ordre, changement de mode dans boite_noire.csv
AU2 ◀──LoRa──▶ boîtier sol : position, alertes ; ATTERRISSAGE, RETOUR_MAISON, ARRET_URGENCE
```

### 3.3 Après le vol

AU1 **se désarme seul** une fois posé (immobile 3 s) : AU2 accepte alors une
nouvelle mission. Le dossier du vol (`photos.csv`, `boite_noire.csv`) et les
photos de la caméra partent au PC en Wi-Fi (**TO DO : module Wi-Fi**) et sont
déposés dans `data\vols\entrant\<nom du vol>\`, où le pipeline d'analyse
les reprend.

## 4. Sécurité

| Menace | Parade |
|---|---|
| Mission envoyée sans relecture humaine | **case « J'ai vérifié la mission » obligatoire** dans le planificateur ; elle se décoche à chaque modification et après chaque envoi |
| Mission incohérente | contrôles du planificateur (polygones, chemin dans les limites et hors zones, altitudes, vitesses, capacités, **culture**) ; envoi impossible si un contrôle est en erreur |
| Corruption pendant le transfert ou dans la mémoire d'AU2 | CRC16 par trame, accusé par élément, **relecture complète octet par octet**, CRC de mission vérifié par AU2 |
| Changement de mission en vol | AU2 refuse `MISSION_DEBUT` (`ETAT_INCOMPATIBLE`) tant que le drone est **armé ou en vol** ; le câble USB n'est de toute façon branché qu'au sol |
| Pas de nouvelle mission possible après le vol | **désarmement automatique** d'AU1 posé et immobile depuis 3 s ; AU2 accepte alors la mission suivante |
| Danger en vol (personne menacée, drone hors de contrôle) | **arrêt d'urgence** par LoRa : `ARRET_URGENCE` coupe les moteurs ; **double confirmation** (deux ordres distincts en moins de 2 s) contre une coupure accidentelle ; interrupteur physique au sol |
| Arrêt sans chute | ordre `ATTERRISSAGE` (lent, sur place) ou `RETOUR_MAISON` |
| Perte de la liaison AU1 ↔ AU2 | AU1 : atterrissage lent ; AU2 : alerte dans la boîte noire et par LoRa |
| Pilotage à distance par un tiers | aucun message de pilotage manuel n'est accepté (`COMMANDE_MANUELLE` réservé, non utilisé) |
| Panne inexpliquée | **boîte noire** : toute alerte, erreur, ordre et changement de mode est écrit et synchronisé sur la carte SD d'AU2 |

## 5. Robustesse

| Situation | Comportement |
|---|---|
| Ouverture du port USB | la Mega redémarre (DTR) : le planificateur attend 2 s avant la première trame |
| Câble USB débranché | le planificateur l'affiche (« AU2 : déconnecté ») ; un transfert en cours échoue proprement, la mission n'est pas validée |
| Trame abîmée | rejetée (CRC) ; l'élément est réémis (5 fois au plus) ; côté drone : alerte `ERREUR_LIAISON` dans la boîte noire |
| AU2 armé ou en vol | envoi refusé, message clair « posez et désarmez le drone » |
| Carte SD en panne | alerte `DEFAUT_SD` par LoRa, retour maison (le vol n'aurait plus de valeur pour l'analyse) |
| Coupure de courant pendant l'écriture | chaque ligne est synchronisée : seule la ligne en cours est perdue |
| Alerte perdue pendant une coupure AU1 ↔ AU2 | les alertes actives sont réémises toutes les 5 s : elles sont rattrapées |
| Archivage impossible (dossier absent, serveur non lancé) | erreur affichée et journalisée ; la mission reste chargée dans AU2 ; l'enregistrer à la main |
| Identifiant de mission déjà archivé | le planificateur en prend un libre ; s'il est pris malgré tout, suffixe `_2`, `_3` (jamais d'écrasement) |

## 6. Paramètres : où les régler

| Paramètre | Planificateur `js/config.js` | AU2 (`ProtocoleDrone.h` / croquis) |
|---|---|---|
| waypoints max | `capacites.maxWaypoints` 150 | `MAX_WAYPOINTS` 150 |
| zones max, sommets | 8, 30, 16 | `MAX_ZONES`, `MAX_SOMMETS_*` |
| hauteur min / max | 2 / 50 m | — (dans `MISSION_DEBUT`) |
| vitesse max | 8 m/s | — |
| caméra (capteur, focale, cadence) | `camera` (**provisoire**, `cameraProvisoire: true`) | TO DO selon la caméra |
| cultures | `cultures` (ble, mais, pommier) | — (non transmise) |
| liaison USB | `serie` : 115 200 bauds, attente 2 s, délai 500 ms | `Serial` 115 200 |
| heartbeat, délais, désarmement | — | `PERIODE_HEARTBEAT_MS` 500, `DELAI_PERTE_LIAISON_MS` 2000, `DELAI_DESARMEMENT_SOL_MS` 3000 |
| arrêt d'urgence | — | `CLE_ARRET_URGENCE`, `DELAI_CONFIRMATION_ARRET_MS` 2000 |
| dossier d'archive | — | `serveur_local.py --missions DOSSIER` (défaut : data\missions) |

## 7. Choix des bibliothèques

| Besoin | Choix | Pourquoi | Écarté |
|---|---|---|---|
| Carte web | **Leaflet 1.9** (copié dans `lib/`) | 40 ko, stable, sans compilation ni clé | OpenLayers (plus lourd), Mapbox/Google (clé, coût) |
| Fonds de carte | **IGN Géoplateforme** (WMTS) | orthophotos 20 cm gratuites en France, sans clé (licence Etalab 2.0), plus RPG et cadastre | fonds payants ou avec clé |
| Page web | **JavaScript (modules ES), sans framework** | aucune installation pour l'utiliser ; tests avec `node --test` | React/Vue + bundler (chaîne d'outils à maintenir) |
| PC ↔ AU2 | **Web Serial** (Chrome, Edge) sur le câble USB | rien à installer ; liaison la plus simple et la plus fiable au sol | Bluetooth (module de plus, appairage) ; Wi-Fi (module à choisir, sera repris quand il sera choisi) |
| Service local | **Python `http.server`** (bibliothèque standard) | Web Serial exige `https` ou `localhost` ; la page ne peut pas écrire seule dans un dossier : le serveur archive à sa place | serveur Node/Apache (installation) |
| Arduino | **en-têtes C++ seuls** | aucune allocation dynamique, structures `packed` = charge utile, testés sur PC ; pas de `printf("%f")` (absent sur AVR) | bibliothèque avec `String` (fragmentation de la RAM) |
| Carte SD | **SdFat** (Bill Greiman) | noms longs (`boite_noire.csv`), `sync()` après chaque ligne, plus rapide que `SD.h` | `SD.h` (noms 8.3 seulement) |
| Tests | `node --test`, `unittest` (Python), g++ sur PC | rien à installer en plus de Node et Python | — |
