# TP — Le planificateur de mission et le protocole du drone agricole

Ce TP fait construire, étape par étape, ce qui prépare le vol : le
planificateur web (carte, quadrillage, calculs, vérifications) et le dialogue
avec AU2, la carte Arduino Mega de navigation qui reçoit la mission. Il
s'adresse à quelqu'un d'**à l'aise en électronique et en C++** : chaque notion
nouvelle est reliée à son équivalent C++ ou Arduino.

Le TP est construit **à partir du code du projet** : ce que vous écrivez dans
les exercices est une version réduite d'une pièce du projet, et la
**correction** de chaque étape renvoie à la pièce complète, expliquée.

## Déroulement

| Étape | Titre | Durée indicative | Matériel | État |
|---|---|---|---|---|
| [4](etape_04_carte_web.md) | Page web : carte, tracé des limites et des zones | 5 h | PC, Chrome | disponible |
| [5](etape_05_chemin_quadrillage.md) | Page web : chemin manuel et quadrillage automatique, calculs, vérifications | 6 h | PC, Chrome | disponible |
| A | Protocole commun en C++ : trames, CRC, décodeur, tests sur PC (`protocole/arduino/test_hote`) | 5 h | PC, AU2 | **à écrire** |
| B | Liaison AU2 ↔ AU1 : heartbeats, perte de liaison, alertes (croquis `tp2_trames`) | 4 h | AU1, AU2 | **à écrire** |
| C | Transmission et relecture de la mission PC → AU2 par le câble USB (Web Serial, croquis `banc_au2_mission`) | 5 h | PC, AU2 | **à écrire** |
| D | Journal de vol sur la carte SD : `photos.csv` et boîte noire (croquis `au2_journal_vol`) | 4 h | AU2, lecteur SD | **à écrire** |
| E | Arrêt d'urgence et désarmement automatique | 3 h | AU1, AU2, boîtier sol | **à écrire** |
| F | Caméra : déclenchement par AU2 et nom de fichier imposé | — | caméra (modèle à choisir) | **TO DO** |
| G | Essais intégrés avec le vrai drone, analyse des journaux | 2 à 4 séances | drone complet | **à écrire** |

Les numéros 4 et 5 sont conservés pour ne pas casser les liens des exercices
web. Les étapes A à G remplacent les anciennes étapes, devenues sans objet
avec l'architecture AU1/AU2 (elles restent consultables dans l'historique git,
étiquette `s21-fe-final`) ; leur code de référence est déjà dans le dépôt.

Chaque étape suit le même plan :

1. **Objectif et ce qui sera testable** ;
2. **Notions et fonctions** : la théorie utile, de courts exemples de syntaxe, le lien avec le C++ ;
3. **Tâche** : cahier des charges, contraintes, critères de réussite, bonus ;
4. **Test** : comment vérifier soi-même ;
5. **Correction** : le code de référence expliqué — **à la fin, nettement séparée**. Ne la lisez
   qu'après avoir terminé, ou après avoir bloqué une bonne demi-heure.

## Où l'on travaille

| Type d'exercice | Vous écrivez dans… | Vous vérifiez avec… | La correction est dans… |
|---|---|---|---|
| Web (étapes 4, 5) | `tp/exercices_web/etape0N/` | `npm test` dans `tp/exercices_web` et Chrome | `tp/corrections/web/` (`npm run test:corrections`) |
| Arduino | croquis fournis | tests sur PC (`make -C protocole/arduino/test_hote`) et moniteur série | `protocole/arduino/exemples/` |
| Le projet complet | — | [docs/tests.md](../../../docs/tests.md) | `planificateur/`, `protocole/` |

Les tests sont les **critères de réussite** : au départ, tous échouent
(« À compléter » en JavaScript) ; une étape est réussie quand ses tests
passent **et** que l'essai sur le matériel donne le résultat attendu.

Conseil : travaillez sur une branche à vous, pour garder la version d'origine
sous la main :

```bash
git checkout -b tp-tom
```

## Matériel et logiciels

* PC Windows 10/11, macOS ou Linux ; **Arduino IDE** ou `arduino-cli` ;
  **Python 3** ; **Node.js 20+** ; **Chrome** ou Edge (Web Serial).
* Deux **Arduino Mega 2560** (AU1 et AU2) et leurs câbles USB.
* Un lecteur de carte **SD** SPI et une carte (étape D).
* Le drone pour l'étape G.

## Rappels utiles

| Je veux… | Commande / fichier |
|---|---|
| lancer les tests web | `cd tp/exercices_web && npm test` (ou `npm run test:corrections`) |
| ouvrir les pages web du TP | `tp/exercices_web/lancer.bat` ou `./tp/exercices_web/lancer.sh` |
| lancer les tests du protocole en C++ | `make -C protocole/arduino/test_hote` |
| la spécification du protocole | [protocole/SPECIFICATION.md](../protocole/SPECIFICATION.md) |
