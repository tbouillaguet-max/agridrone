# Tests

## 1. Tests automatiques

| Suite | Commande (depuis la racine du dépôt) | Ce qui est vérifié |
|---|---|---|
| Planificateur (JavaScript) | `cd planificateur && npm test` | protocole contre les vecteurs, géométrie, quadrillage (sécurité sur 60 terrains aléatoires, couverture), vérifications, fichier JSON, **culture** (enregistrée, contrôlée, obligatoire, jamais transmise au drone), transfert vers AU2 simulé (pertes, relecture qui détecte un stockage défaillant, **refus si armé puis acceptation après désarmement**) |
| Archivage (Python) | `python -m unittest discover -s planificateur/tests -p "test_*.py"` | `serveur_local.py` : archivage, suffixes sans écrasement, refus explicites (culture absente ou inconnue, identifiant incohérent, JSON invalide), identifiant libre, journal sur disque, aller-retour HTTP |
| En-têtes Arduino (C++) | `make -C protocole/arduino/test_hote` | `ProtocoleDrone.h` contre les vecteurs (tailles des structures, CRC, codage, décodage, flux bruité, doublons, **double confirmation de l'arrêt d'urgence**) ; `FichiersVol.h` : lignes de `photos.csv` et `boite_noire.csv` **exactement** conformes au contrat |
| Fichiers d'un vol | `python protocole/outils/verifier_fichiers_vol.py protocole/exemples_fichiers/vol_exemple` | le contrôleur accepte le vol d'exemple ; sur un vrai vol : `… <dossier du vol> --mission <mission_<id>.json>` |
| Vecteurs de test | `python3 protocole/outils/generer_vecteurs.py` puis `git diff` | régénère `vecteurs_test.json` et `vecteurs_test.h` de façon indépendante : aucune différence attendue |
| Corrections du TP (web) | `cd tp/exercices_web && npm run test:corrections` | 9 tests des étapes 4 et 5 |

Tout lancer d'un coup (Linux, macOS, WSL) :

```bash
(cd planificateur && npm test) \
  && python3 -m unittest discover -s planificateur/tests -p "test_*.py" \
  && make -C protocole/arduino/test_hote \
  && python3 protocole/outils/verifier_fichiers_vol.py protocole/exemples_fichiers/vol_exemple \
  && (cd tp/exercices_web && npm run test:corrections)
```

## 2. Test croisé : planificateur (JavaScript) → banc AU2 (C++), sur PC

Le croquis `protocole/arduino/exemples/banc_au2_mission` (réception de
mission, relecture, CRC, refus si armé, arrêt d'urgence) tourne **sur le PC**,
compilé tel quel avec une petite émulation de l'API Arduino
(`test_hote/arduino_hote.h`) : `Serial` (le câble USB) y est un serveur TCP.

```bash
make -C protocole/arduino/test_hote banc
./protocole/arduino/test_hote/banc_hote 5761                       # terminal 1
cd planificateur && BANC_AU2=127.0.0.1:5761 npm test               # terminal 2
```

Le test « transfert vers le banc AU2 en C++ » envoie une mission avec le code
du planificateur (`transfert.js`) au récepteur C++ : l'émetteur JavaScript et
le récepteur Arduino sont ainsi vérifiés l'un contre l'autre. Avec
`BANC_ARME=1 ./protocole/arduino/test_hote/banc_hote 5761`, le même test doit
**échouer** avec « drone armé ou en vol ».

## 3. Compiler les croquis Arduino

Avec l'IDE Arduino : copier `protocole/arduino/ProtocoleDrone` dans
`Documents/Arduino/libraries/`, installer **SdFat** (gestionnaire de
bibliothèques) pour `au2_journal_vol`, ouvrir le croquis, carte *Arduino Mega
or Mega 2560*. Avec `arduino-cli` :

```bash
arduino-cli core install arduino:avr
arduino-cli lib install SdFat
for c in tp2_trames banc_au2_mission au2_journal_vol; do
  arduino-cli compile --fqbn arduino:avr:mega --library protocole/arduino/ProtocoleDrone \
    --warnings all protocole/arduino/exemples/$c
done
```

`banc_au2_mission` garde la mission complète en RAM (environ 4,1 ko sur 8 ko) :
suffisant pour un banc ; le programme de vol d'AU2 stockera les waypoints en
EEPROM.

## 4. Essais de bout en bout sans drone

### A. Planificateur seul

1. `planificateur/lancer.bat` (ou `lancer.sh`), *Ouvrir…*
   `exemples/mission_exemple.json` : 0,4 ha, 10 passes, 32 waypoints, culture
   blé, toutes les vérifications vertes (« Paramètres de la caméra » en
   avertissement tant que la caméra n'est pas choisie).
2. *AU2 simulé*, cocher « J'ai vérifié… », *Envoyer la mission* : envoi,
   relecture, fin, « Mission N chargée dans AU2 », puis
   « Archivée : …\data\missions\mission_N.json ».
3. Vider la culture : vérification « Culture » rouge, envoi impossible.
4. Console du navigateur : `planificateur.au2Simule.arme = true` ; l'état
   passe à « ARMÉ » ; un envoi est refusé (« drone armé ou en vol ») et la
   ligne apparaît dans `journal_planificateur.txt`.

### B. Avec la vraie Mega (croquis `banc_au2_mission`)

Montage : [cablage.md](cablage.md).

| Action | Résultat attendu |
|---|---|
| *Connecter AU2 (câble USB)* | journal : « AU2 (banc) prêt » ; état « Drone désarmé · mission non chargée » |
| mission envoyée | journal : « réception d'une nouvelle mission », « mission validée (CRC correct) » ; état « mission chargée » ; archivage |
| broche 22 à GND puis nouvel envoi | état « ARMÉ » ; refus « drone armé ou en vol » |
| broche 22 relâchée (désarmement) puis envoi | mission acceptée |
| câble débranché pendant un envoi | « AU2 déconnecté (câble USB débranché) » ; mission non validée |

### C. Arrêt d'urgence (banc ou AU1/AU2 réels, hélices démontées)

| Action | Résultat attendu |
|---|---|
| un seul `ARRET_URGENCE` | `ACK` ; « en attente de confirmation » ; moteurs **non** coupés |
| deux `ARRET_URGENCE` de séquences différentes à moins de 2 s | moteurs coupés, désarmé, `ALERTE_AVARIE` 0x11 ; ligne `ORDRE` puis `ALERTE` dans la boîte noire |
| deux ordres à plus de 2 s | pas de coupure (la seconde redevient une première demande) |
| la même trame réémise (même séquence) | pas de coupure |
