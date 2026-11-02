# Module : `systeme-gps`

> Dossier : `src/modules/systeme-gps/`. Étapes du banc d'essai : en-têtes des scripts.

## 1. Rôle
Banc d'essai matériel pour récupérer le GPS et le compas du DJI Phantom 3 : écoute brute du GPS à travers le pont USB-série d'un Arduino Uno, scan I2C pour identifier le compas.

## 2. Interfaces (Contrat d'entrée/sortie)
- **Point d'entrée** : `GPS.py` (étape 2, version COM5) et `GPS2.py` (même étape, décodage UBX en option) ; croquis `GPS_Arduino/GPS_Arduino.ino` (étape 1, scanner I2C).
- **Entrées** : flux série du GPS (NMEA ou UBX) sur un port COM ; bus I2C du compas.
- **Sorties** : affichage console (vitesses détectées, phrases NMEA, messages UBX). Aucun fichier de contrat.

## 3. Dépendances Déclarées
- **Consomme** : aucun
- **Fournit à** : `au1-au2` (futur : choix et pilotage du GPS et du compas)
- **Données (`data/`)** : aucune

## 4. Commandes Propres
Depuis `src/modules/systeme-gps/`.
- **Techno** : Python (pyserial) + Arduino
- **Installer** : `pip install pyserial` ; Arduino IDE pour le croquis
- **Lancer** : `python GPS2.py COM3 [--baud 9600] [--ubx]`
- **Tests** : aucun (essais sur matériel)

## 5. Règle d'Isolation (Interdits)
- Ne rien brancher avant confirmation des couleurs de fils (voir en-têtes des scripts) ; aucune ligne 5 V vers le GPS.
- `GPS.py` et `GPS2.py` sont deux versions de la même étape : en garder une seule quand le port et les options sont fixés.
- Ne jamais importer ce module depuis un autre.
