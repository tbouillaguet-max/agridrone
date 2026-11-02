# Notice — Protocole commun et fichiers de vol d'AU2 (v2)

Module : `src\modules\protocole\` (spécification, en-têtes C++ pour Arduino, outils).
Position dans le workflow : entre le planificateur (amont) et le pipeline d'analyse (aval). Le programme de vol d'AU1/AU2 (autre dépôt) doit l'utiliser.

## 1. Composants
| Fichier | Rôle |
|---|---|
| `SPECIFICATION.md` | référence : trames `AA 55`, messages, cycle de vie, arrêt d'urgence, fichiers de la carte SD (§ 12) |
| `arduino/ProtocoleDrone/ProtocoleDrone.h` | constantes, structures, CRC, décodeur, `ConfirmationArretUrgence` |
| `arduino/ProtocoleDrone/FichiersVol.h` | mise en forme exacte des lignes de `photos.csv` et `boite_noire.csv` (sans `printf("%f")`) |
| `arduino/exemples/banc_au2_mission` | AU2 minimal : réception de mission, refus si armé, arrêt d'urgence |
| `arduino/exemples/au2_journal_vol` | écriture SD (SdFat), dossier par vol, `sync()` après chaque ligne |
| `arduino/exemples/tp2_trames` | liaison AU2 ↔ AU1, heartbeats, perte de liaison |
| `outils/verifier_fichiers_vol.py` | contrôle d'un dossier de vol contre le contrat |

## 2. Liaisons
PC ↔ AU2 : câble USB (`Serial`), au sol. AU2 ↔ AU1 : `Serial1`, 115 200 bauds. AU2 ↔ sol : LoRa. Émetteurs : AU2 = 0x00, AU1 = 0x05.

## 3. Entrées d'AU2
- Mission du planificateur (protocole § 6.5, § 8.2).
- Alertes et télémétrie d'AU1 ; ordres du sol (ATTERRISSAGE, RETOUR_MAISON, ARRET_URGENCE).

## 4. Sorties d'AU2 (contrat avec le pipeline — ne pas modifier sans prévenir)
Dossier par vol sur la SD : `/vols/mission_<id 5 chiffres>_<n>/`.

**`photos.csv`** (inchangé par rapport à la notice du pipeline) :
`fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission`
- `fichier` imposé par AU2 : `IMG_0001.JPG`… ; lat/lon 7 décimales WGS84 ; altitude 2 décimales ; cap 1 décimale ; `index_waypoint` = dernier waypoint atteint.
- Pas d'heure GPS ⇒ pas de ligne (alerte GPS_PERDU dans la boîte noire).

**`boite_noire.csv`** (nouveau) :
`horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail`
Toute alerte (AU1, AU2, tourelle), ordre reçu, armement/désarmement, mission reçue/refusée/validée, erreur de liaison, démarrage, défaut SD ou caméra.

## 5. Sécurité
- Nouvelle mission refusée tant que le drone est armé ou en vol ; **désarmement automatique** après 3 s posé ⇒ mission suivante acceptée.
- **ARRET_URGENCE (0x24)** : coupe les moteurs ; depuis le sol, deux ordres de séquences différentes en moins de 2 s ; AU2 → AU1 une seule trame.
- Perte AU1 ↔ AU2 > 2 s : AU1 atterrit lentement.

## 6. TO DO
Interface caméra (déclenchement, nom imposé) selon le modèle ; transfert Wi-Fi vers `data\vols\entrant\<vol>\`.

## 7. Tests
`make -C protocole/arduino/test_hote` ; `python protocole/outils/verifier_fichiers_vol.py protocole/exemples_fichiers/vol_exemple`.
