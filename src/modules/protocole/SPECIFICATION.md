# Protocole de communication commun — spécification (version 1)

Ce document est **la référence** : le planificateur web (PC) et le code
Arduino (AU1, AU2, Uno de la tourelle, boîtier sol LoRa) doivent tous s'y
conformer octet pour octet. Les implémentations du dépôt sont vérifiées contre
les mêmes [vecteurs de test](vecteurs_test.json).

| Implémentation | Fichiers |
|---|---|
| JavaScript (planificateur web) | `planificateur/js/protocole.js` |
| C++ (Arduino) | `protocole/arduino/ProtocoleDrone/ProtocoleDrone.h` |
| C++ (Arduino, fichiers de la carte SD d'AU2) | `protocole/arduino/ProtocoleDrone/FichiersVol.h` |
| Python (génération des vecteurs de test) | `protocole/outils/generer_vecteurs.py` |
| Python (contrôle des fichiers d'un vol) | `protocole/outils/verifier_fichiers_vol.py` |

---

## 1. Liaisons

```
 PC (Chrome, planificateur)        AU2 (Arduino Mega)                  AU1 (Arduino Mega)
 ┌──────────────────────┐ câble   ┌─────────────────────────┐ Serial1  ┌──────────────────┐
 │ tracé, quadrillage,  │  USB    │ navigation, GPS,        │ ───────▶ │ pilotage,        │
 │ vérifications, JSON, │ ──────▶ │ magnétomètre, mission,  │ ◀─────── │ stabilisation,   │
 │ archivage            │ ◀────── │ caméra, carte SD,       │ 115200   │ moteurs (ESC),   │
 └──────────────────────┘ Serial  │ LoRa, boîte noire       │          │ failsafes        │
        ▲  au sol uniquement      └─────────────────────────┘          └──────────────────┘
        │                            │ LoRa        │ déclenchement
        │ Wi-Fi après l'atterrissage ▼             ▼
        └──── photos + photos.csv  boîtier sol    caméra (modèle à choisir)
              + boite_noire.csv    (ordres, alertes)
```

| Liaison | Support | Paramètres | Quand |
|---|---|---|---|
| PC ↔ AU2 | **câble USB** (port USB de la Mega = `Serial`), ouvert par Chrome avec Web Serial | 115 200 bauds, 8N1 | au sol, pour charger la mission |
| AU2 ↔ AU1 | UART `Serial1` (TX1 18 / RX1 19), croisée, masses communes | 115 200 bauds, 8N1 | toujours |
| AU2 ↔ boîtier sol | LoRa (un seul module, sur AU2) | autre prompt | en vol |
| AU2 ↔ Uno (tourelle) | UART | autre prompt | en vol |
| AU2 → caméra | déclenchement et nom de fichier imposé | **TO DO : dépend du modèle** | en vol |
| drone → PC | Wi-Fi (module à choisir) : photos, `photos.csv`, `boite_noire.csv` | **TO DO** | après l'atterrissage |

La **même trame** circule sur le câble USB, la liaison AU2 ↔ AU1 et la LoRa.
Il n'y a ni réseau mobile, ni pilotage manuel à distance : en vol, la seule
liaison sol est la LoRa d'AU2 (position, alertes ; ordres ATTERRISSAGE,
RETOUR_MAISON et ARRET_URGENCE).

Au démarrage d'un port USB, la Mega redémarre (signal DTR) : le PC attend
**2 s** après l'ouverture du port avant d'envoyer la première trame.

---

## 2. Format de la trame

| Décalage | Taille | Champ | Description |
|---:|---:|---|---|
| 0 | 1 | `synchro1` | toujours `0xAA` |
| 1 | 1 | `synchro2` | toujours `0x55` |
| 2 | 1 | `version` | version du protocole, **`1`** |
| 3 | 1 | `type` | type de message (§ 5) |
| 4 | 2 | `sequence` | u16 little-endian, numéro de séquence de l'émetteur |
| 6 | 1 | `longueur` | N = nombre d'octets de données (0 à 255) |
| 7 | N | `donnees` | charge utile (§ 6) |
| 7+N | 2 | `crc` | CRC16 little-endian |

Taille totale : **9 + N octets** (9 à 264).

### 2.1 CRC16

* **CRC-16/CCITT-FALSE** : polynôme `0x1021`, valeur initiale `0xFFFF`,
  pas de réflexion, pas de XOR final.
* Calculé du champ `version` jusqu'à la fin des données (décalages 2 à 6+N) :
  les deux octets de synchro ne sont **pas** inclus.
* Transmis en little-endian. Valeur de contrôle : `CRC("123456789") = 0x29B1`.

```c
uint16_t crc16(const uint8_t *d, size_t n, uint16_t crc /* = 0xFFFF */) {
  while (n--) {
    crc ^= (uint16_t)(*d++) << 8;
    for (uint8_t i = 0; i < 8; i++)
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}
```

### 2.2 Décodage d'un flux

Sur chaque liaison série comme sur la LoRa, le récepteur voit un **flux d'octets** et le
découpe avec une machine à états :

```
ATTENTE_AA → ATTENTE_55 → VERSION → TYPE → SEQ_L → SEQ_H → LONGUEUR → DONNEES (N) → CRC_L → CRC_H
```

* En `ATTENTE_55`, un nouvel `0xAA` laisse dans `ATTENTE_55` (cas `AA AA 55`) ;
  tout autre octet ramène à `ATTENTE_AA`.
* Une version différente de 1 ramène à `ATTENTE_AA` (compteur « erreurs version »).
* CRC faux : trame jetée (compteur « erreurs CRC »), retour en `ATTENTE_AA`.
* Recommandé : une trame commencée et non terminée après 100 ms est abandonnée.

### 2.3 Numéros de séquence

* Chaque émetteur tient, **par liaison**, un compteur u16 incrémenté à chaque
  nouvelle trame (65535 → 0).
* Une **réémission** (élément non acquitté) réutilise **le même** numéro : le
  récepteur ré-acquitte sans ré-exécuter (les éléments de mission sont de toute
  façon idempotents : recevoir deux fois le même waypoint ne change rien).
* `ACK`/`NACK` citent le type et la séquence de la trame concernée.
* Détection de doublon conseillée pour les commandes : *même type et même
  séquence reçus il y a moins de 3 s ⇒ doublon*.

### 2.4 Conventions

* Entiers multi-octets en **little-endian**.
* Coordonnées : `int32`, **degrés × 10⁷** (`latitude_e7`, `longitude_e7`).
* Altitudes et distances : **centimètres** (`_cm`) ; altitudes en `int32`.
* Angles : **centidegrés** (`_cdeg`) ; caps dans `[0, 35999]` (u16), roulis et
  tangage dans `[-18000, 18000]` (i16).
* Vitesses : cm/s (`_cms`). Durées : ms (`_ms`) ou µs (`_us`).
* Valeur « inconnue » : `0xFFFF` (u16), `0xFF` (u8), `0x7FFF` (i16), sauf mention.

---

## 3. Identifiants d'émetteurs

Utilisés dans `HEARTBEAT.emetteur`, `TEXTE.source`, `ALERTE_AVARIE.source`
et dans la colonne `source` de la boîte noire (§ 12.3).

| Valeur | Émetteur | Nom (boîte noire) |
|---|---|---|
| `0x00` | AU2 — navigation, capteurs, mission, LoRa, carte SD | `AU2` |
| `0x01` | Arduino Uno (tourelle ultrason) | `TOURELLE` |
| `0x02` | *retiré, réservé : ne pas réutiliser* | — |
| `0x03` | Boîtier sol LoRa | `SOL` |
| `0x04` | Planificateur de mission (PC) | `PC` |
| `0x05` | AU1 — pilotage, stabilisation, moteurs | `AU1` |
| `0xFF` | Inconnu | `INCONNU` |

---

## 4. Heartbeats, délais, cycle de vie

| Heartbeat | Période | Délai de perte (paramétrable) | Conséquence |
|---|---|---|---|
| AU2 → AU1 | 500 ms | 2 s côté AU1 | avarie `PERTE_LIAISON_AU2` (0x0E) : **atterrissage lent** (failsafe) |
| AU1 → AU2 | 500 ms | 2 s côté AU2 | avarie `PERTE_LIAISON_AU1` (0x0D) : écrite dans la boîte noire, envoyée par LoRa |
| AU2 → PC (câble) | 500 ms | — | le planificateur affiche « AU2 armé » ou « mission chargée » |

Le heartbeat est émis par la boucle principale : si le programme se bloque,
les heartbeats cessent et l'autre carte le détecte.

### 4.1 Cycle de vie d'une mission

```
 désarmé ──(mission reçue, relue, MISSION_FIN OK)──▶ désarmé + mission chargée
    ▲                                                     │ armement, décollage
    │                                                     ▼
 désarmement automatique ◀── atterrissage ◀── vol (mission, retour, atterrissage)
 (posé et immobile 3 s)
```

* AU2 **refuse** `MISSION_DEBUT` (statut `ETAT_INCOMPATIBLE`) tant que le
  drone est **armé ou en vol** (drapeaux § 7.3, tenus par AU1 et recopiés par AU2).
* **Désarmement automatique** : AU1 désarme quand le drone est posé —
  altitude relative < 0,3 m, vitesse verticale nulle, gaz au minimum — depuis
  `DELAI_DESARMEMENT_SOL_MS` = **3 s**. Il l'annonce dans son heartbeat ; AU2
  l'écrit dans la boîte noire (catégorie `MODE`).
* Une fois désarmé, AU2 **accepte une nouvelle mission** : elle remplace la
  précédente, et le vol suivant ouvre un nouveau dossier sur la carte SD (§ 12.1).
* L'**arrêt d'urgence** (§ 6.3) coupe les moteurs et désarme immédiatement,
  en vol comme au sol.

---

## 5. Liste des types

**Origine** : *base* = type du cahier des charges ; *adapté* = type du cahier
des charges dont le contenu est précisé ici ; **ajouté** = nouveau type
(à reporter côté Arduino, voir § 10).
**Usage** : *USB* = PC ↔ AU2 (câble) ; *AU* = AU2 ↔ AU1 ; *LoRa* = AU2 ↔
boîtier sol ; *autre* = tourelle.

| Id | Nom | Sens | Taille | Usage | Origine |
|---|---|---|---:|---|---|
| `0x01` | `HEARTBEAT` | tous | 6 | USB, AU, autre | base |
| `0x02` | `ACK` | tous | 3 | USB, AU, LoRa | base |
| `0x03` | `NACK` | tous | 4 | USB, AU, LoRa | base |
| `0x04` | `TEXTE` | tous | 2+n | USB, AU | **ajouté** |
| `0x10` | `TELEMETRIE` | AU2 → sol ; AU1 → AU2 | 47 | LoRa, AU | base |
| `0x11` | `ALERTE_AVARIE` | AU1 → AU2 ; AU2 → sol, PC | 7 | AU, LoRa, USB | base |
| `0x12` | `DISTANCES_TOURELLE` | Uno → AU2 | 5+2k | autre | base |
| `0x20` | `COMMANDE_MODE` | sol → AU2 → AU1 | 1 | LoRa, AU | base |
| `0x21` | `COMMANDE_MANUELLE` | — | 8 | non utilisé (pas de pilotage manuel) | base |
| `0x22` | `ATTERRISSAGE` | sol → AU2 → AU1 | 0 | LoRa, AU | base |
| `0x23` | `RETOUR_MAISON` | sol → AU2 | 0 | LoRa | base |
| `0x24` | `ARRET_URGENCE` | sol → AU2 → AU1 | 2 | LoRa, AU | **ajouté** |
| `0x40` | `MISSION_DEBUT` | PC → AU2 | 12 | USB | adapté |
| `0x41` | `MISSION_LIMITES` | PC → AU2 | 3+8n | USB | **ajouté** |
| `0x42` | `ZONE_INTERDITE` | PC → AU2 | 4+8n | USB | adapté |
| `0x43` | `MISSION_WAYPOINT` | PC → AU2 | 19 | USB | base |
| `0x44` | `MISSION_FIN` | PC → AU2 | 4 | USB | adapté |
| `0x45` | `MISSION_ACK` | AU2 → PC | 6 | USB | adapté |
| `0x46` | `MISSION_VERIFICATION` | PC → AU2 | 5 | USB | **ajouté** |

**Identifiants retirés, réservés (ne jamais réutiliser)** : `0x30`, `0x31`
(photo : le déclenchement de la caméra est désormais interne à AU2), `0x47`,
`0x50`.

Plages réservées : `0x25`–`0x2F` (autres commandes : armement, décollage…),
`0x13`–`0x1F` (autres télémesures).

Un récepteur ignore un type inconnu (et peut répondre `NACK TYPE_INCONNU`).
Charge utile **plus longue** que prévu : octets en trop ignorés (compatibilité
future). **Plus courte** : `NACK FORMAT`.

---

## 6. Charges utiles

Notation : `u8/u16/u32` non signés, `i16/i32` signés, little-endian.

### 6.1 Liaison

#### `0x01 HEARTBEAT` (6 octets)

| Déc. | Type | Champ | Description |
|---:|---|---|---|
| 0 | u8 | `emetteur` | § 3 |
| 1 | u8 | `etat` | drapeaux de télémétrie (§ 7.3) |
| 2 | u32 | `temps_ms` | temps depuis le démarrage de l'émetteur |

#### `0x02 ACK` (3 octets)

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u8 | `type_acquitte` |
| 1 | u16 | `sequence_acquittee` |

#### `0x03 NACK` (4 octets)

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u8 | `type_refuse` |
| 1 | u16 | `sequence_refusee` |
| 3 | u8 | `code` (§ 7.5) |

#### `0x04 TEXTE` (2 + n octets, n ≤ 200) — ajouté

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u8 | `gravite` (0 debug, 1 info, 2 avertissement, 3 erreur) |
| 1 | u8 | `source` (§ 3) |
| 2 | n | texte UTF-8, sans zéro final |

Messages lisibles pour le journal du planificateur (« Mission validée »,
« Mission refusée : drone armé »…). Sur le câble USB, AU2 n'envoie **que des
trames** : jamais de texte brut (pas de `Serial.print` vers le PC).

### 6.2 État du drone

#### `0x10 TELEMETRIE` (47 octets)

Émise par AU2 vers le boîtier sol LoRa (autre prompt), et par AU1 vers AU2
(attitude, moteurs, batterie). AU2 complète la position et le cap.

| Déc. | Type | Champ | Unité / description |
|---:|---|---|---|
| 0 | u32 | `temps_ms` | temps de l'émetteur |
| 4 | i16 | `roulis_cdeg` | |
| 6 | i16 | `tangage_cdeg` | positif = nez vers le haut |
| 8 | u16 | `lacet_cdeg` | cap 0–35999 (0 = nord) |
| 10 | i32 | `latitude_e7` | |
| 14 | i32 | `longitude_e7` | |
| 18 | i32 | `altitude_msl_cm` | altitude GPS au-dessus du niveau de la mer |
| 22 | i32 | `altitude_relative_cm` | au-dessus du point de départ |
| 26 | u16 | `vitesse_sol_cms` | |
| 28 | i16 | `vitesse_verticale_cms` | positive vers le haut |
| 30 | u16 | `route_cdeg` | direction du déplacement sol |
| 32 | u16 | `tension_batterie_mv` | |
| 34 | i16 | `courant_batterie_ca` | centiampères |
| 36 | u8 | `batterie_pct` | 0–100, 255 inconnu |
| 37 | u8 | `mode_vol` | § 7.1 |
| 38 | u8 | `etat_gps` | § 7.2 |
| 39 | u8 | `nb_satellites` | |
| 40 | u16 | `hdop_x100` | |
| 42 | u8 | `drapeaux` | § 7.3 |
| 43 | u16 | `waypoint_courant` | `0xFFFF` = aucun |
| 45 | u16 | `photos_declenchees` | depuis le début de la mission |

#### `0x11 ALERTE_AVARIE` (7 octets)

| Déc. | Type | Champ | Description |
|---:|---|---|---|
| 0 | u8 | `code` | § 7.4 |
| 1 | u8 | `gravite` | 0 info, 1 avertissement, 2 critique, 3 urgence |
| 2 | u8 | `source` | § 3 (qui a détecté) |
| 3 | u8 | `action` | action prise ou demandée : 0 aucune, 1 maintien de position, 2 retour maison, 3 atterrissage, 4 coupure moteurs, 5 poursuite |
| 4 | i16 | `valeur` | contextuelle (température en 0,1 °C, tension en dV…) |
| 6 | u8 | `actif` | 1 = l'avarie apparaît/persiste, 0 = elle a disparu |

AU1 envoie ses alertes à AU2, qui les écrit **toutes** dans la boîte noire
(§ 12.3) et les relaie au sol par LoRa. Une alerte active est **réémise
toutes les 5 s** tant qu'elle persiste (une alerte perdue pendant une coupure
de la liaison AU1 ↔ AU2 est ainsi rattrapée), puis une dernière fois avec
`actif = 0`. Toute erreur détectée par AU1 ou AU2 donne une alerte : il n'y a
pas d'erreur silencieuse.

### 6.3 Ordres du sol

Contenus pour que tout le projet partage la même numérotation. Chaque ordre
reçu est **acquitté** (`ACK`) et écrit dans la boîte noire (catégorie `ORDRE`).

| Type | Contenu |
|---|---|
| `0x12 DISTANCES_TOURELLE` | `u8 nb_mesures (k ≤ 32)`, `i16 angle_debut_cdeg`, `i16 pas_cdeg`, `k × u16 distances_cm` (`0xFFFF` = pas d'écho) |
| `0x20 COMMANDE_MODE` | `u8 mode_vol` (§ 7.1) |
| `0x21 COMMANDE_MANUELLE` | `i16 roulis, i16 tangage, i16 lacet, i16 gaz`, consignes normalisées −1000…+1000 (réservé, non utilisé) |
| `0x22 ATTERRISSAGE` | aucune donnée : atterrissage lent sur place |
| `0x23 RETOUR_MAISON` | aucune donnée : retour au point de départ puis atterrissage |
| `0x24 ARRET_URGENCE` | voir ci-dessous |

#### `0x24 ARRET_URGENCE` (2 octets) — ajouté

| Déc. | Type | Champ | Description |
|---:|---|---|---|
| 0 | u16 | `cle` | toujours `0x5AA5` (une autre valeur : `NACK FORMAT`, ordre ignoré) |

**Effet : coupure immédiate des moteurs et désarmement.** En vol, le drone
**tombe** : c'est l'ordre de dernier recours (personne menacée, drone hors de
contrôle). Pour un arrêt sans chute, utiliser `ATTERRISSAGE`.

* **Sol → AU2 (LoRa) : double confirmation.** AU2 n'exécute l'arrêt
  qu'après **deux** trames `ARRET_URGENCE` valides, de **numéros de
  séquence différents**, reçues en **moins de 2 s**. Une réémission (même
  séquence) ne confirme pas. Le boîtier sol envoie donc deux ordres distincts
  (par exemple : appui, puis second appui de confirmation). Chaque trame est
  acquittée ; la première est écrite dans la boîte noire (« en attente de
  confirmation »).
* **AU2 → AU1 (série) : une seule trame suffit.** AU2 la réémet toutes les
  100 ms jusqu'à l'`ACK` d'AU1. AU1 coupe les moteurs **avant** d'acquitter,
  passe en mode `URGENCE`, se désarme et émet `ALERTE_AVARIE`
  `ARRET_URGENCE` (0x11, gravité urgence, action coupure moteurs).
* AU2 écrit l'exécution dans la boîte noire et l'annonce au sol par LoRa.
* Au sol, un **interrupteur physique** sur le drone coupe aussi les moteurs
  et interdit l'armement (sécurité pendant les manipulations).
* Après un arrêt d'urgence, un nouvel armement exige un redémarrage d'AU1
  (pas de reprise automatique).

L'aide `ConfirmationArretUrgence` de `ProtocoleDrone.h` applique la règle de
double confirmation (testée dans `test_hote/test_protocole.cpp`).

### 6.4 Photo

Le déclenchement de la caméra est **interne à AU2** : il n'y a plus de
message photo dans le protocole. Entre un waypoint « début des photos » et le
waypoint « fin des photos » suivant, AU2 déclenche la caméra tous les
`distance_photos_cm` parcourus, lui **impose le nom du fichier**
(`IMG_0001.JPG`, `IMG_0002.JPG`… numérotés à partir de 1 dans chaque vol), et
écrit une ligne de `photos.csv` (§ 12.2). L'interface avec la caméra
(déclenchement, nom de fichier, accusé) est **TO DO : elle dépend du modèle
de caméra programmable retenu**.

### 6.5 Mission

Une mission se compose, **dans cet ordre de transfert** :

1. d'un en-tête `MISSION_DEBUT` ;
2. des limites du terrain `MISSION_LIMITES` (un polygone) ;
3. de `nb_zones` zones interdites `ZONE_INTERDITE` (polygones) ;
4. de `nb_waypoints` waypoints `MISSION_WAYPOINT` ;
5. d'une relecture (`MISSION_VERIFICATION`, § 8.2) ;
6. d'une fin `MISSION_FIN` portant le CRC de l'ensemble.

La mission va **directement du PC à AU2** par le câble USB. AU2 la garde
(sans perte de précision) ; AU1 n'en reçoit que les consignes de vol, au fil
du vol. La **culture** de la parcelle (`ble`, `mais`, `pommier`) est dans le
fichier de mission du PC mais **n'est pas transmise au drone** : elle ne sert
qu'au pipeline d'analyse.

Les éléments 1 à 4 sont **idempotents** : en recevoir un deux fois remplace
simplement l'exemplaire stocké.

#### `0x40 MISSION_DEBUT` (12 octets) — adapté

| Déc. | Type | Champ | Description |
|---:|---|---|---|
| 0 | u16 | `id_mission` | choisi par le planificateur |
| 2 | u16 | `nb_waypoints` | |
| 4 | u8 | `nb_sommets_limites` | 3 … 30 |
| 5 | u8 | `nb_zones` | 0 … `max_zones` |
| 6 | u16 | `distance_photos_cm` | espacement des déclenchements entre « début » et « fin » des photos (0 = pas de déclenchement automatique) |
| 8 | u16 | `vitesse_cms` | vitesse de croisière par défaut |
| 10 | u8 | `options` | bit 0 : retour maison à la fin ; bit 1 : atterrir sur place à la fin ; sinon stationnaire au dernier point |
| 11 | u8 | `hauteur_max_m` | plafond de la mission (m au-dessus du départ) |

Réception d'un `MISSION_DEBUT` : la mission précédente est **invalidée** et un
nouveau chargement commence. AU2 le refuse (`ETAT_INCOMPATIBLE`) si le drone
est armé ou en vol (§ 4.1).

#### `0x41 MISSION_LIMITES` (3 + 8n octets, 3 ≤ n ≤ 30) — ajouté

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u16 | `id_mission` |
| 2 | u8 | `nb_sommets` (n) |
| 3 | n × (i32, i32) | `latitude_e7`, `longitude_e7` de chaque sommet |

Polygone **fermé implicitement** (le dernier sommet est relié au premier, sans
le répéter), simple (ses côtés ne se croisent pas). AU2 l'utilise comme
limite de vol (« geofence »).

#### `0x42 ZONE_INTERDITE` (4 + 8n octets, 3 ≤ n ≤ 30) — adapté

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u16 | `id_mission` |
| 2 | u8 | `index_zone` (0 … nb_zones−1) |
| 3 | u8 | `nb_sommets` (n) |
| 4 | n × (i32, i32) | sommets du polygone |

Le planificateur limite les zones à **16 sommets** par défaut (mémoire
d'AU2, paramètre `max_sommets_zone`).

#### `0x43 MISSION_WAYPOINT` (19 octets)

| Déc. | Type | Champ | Description |
|---:|---|---|---|
| 0 | u16 | `id_mission` | |
| 2 | u16 | `index` | 0 … nb−1 |
| 4 | i32 | `latitude_e7` | |
| 8 | i32 | `longitude_e7` | |
| 12 | i32 | `altitude_relative_cm` | au-dessus du point de départ |
| 16 | u16 | `vitesse_cms` | vitesse pour rejoindre ce point |
| 18 | u8 | `action` | § 7.8 : 0 passage, 1 début des photos, 2 fin des photos, 3 photo unique |

Déclenchement : entre un waypoint « début des photos » et le waypoint « fin
des photos » suivant, AU2 déclenche la caméra tous les `distance_photos_cm`
parcourus (une photo exactement sur chacun des deux points). Sur un waypoint
« photo unique », une seule photo à l'arrivée (§ 6.4).

#### `0x44 MISSION_FIN` (4 octets) — adapté

| Déc. | Type | Champ | Description |
|---:|---|---|---|
| 0 | u16 | `id_mission` | |
| 2 | u16 | `crc_mission` | CRC-16/CCITT-FALSE (init `0xFFFF`) enchaîné sur les **données** de `MISSION_DEBUT`, `MISSION_LIMITES`, chaque `ZONE_INTERDITE` (index croissants) puis chaque `MISSION_WAYPOINT` (index croissants) |

Le récepteur vérifie que **tous** les éléments sont présents (sinon
`INCOMPLETE`) et que son propre calcul du CRC est identique (sinon
`CRC_INVALIDE`). Statut `OK` ⇒ la mission est **validée** : bit « mission
chargée » du heartbeat d'AU2, et archivage du fichier de mission sur le PC
(`data\missions\mission_<id>.json`).

#### `0x45 MISSION_ACK` (6 octets) — adapté

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u16 | `id_mission` |
| 2 | u8 | `element` (§ 7.10 : 0 début, 1 limites, 2 zone, 3 waypoint, 4 fin) |
| 3 | u16 | `index` (zone ou waypoint ; 0 pour les autres) |
| 5 | u8 | `statut` (§ 7.6) |

Réponse à chaque élément de mission, à `MISSION_FIN`, et à une
`MISSION_VERIFICATION` impossible à satisfaire.

#### `0x46 MISSION_VERIFICATION` (5 octets) — ajouté (relecture)

| Déc. | Type | Champ |
|---:|---|---|
| 0 | u16 | `id_mission` |
| 2 | u8 | `element` (0 début, 1 limites, 2 zone, 3 waypoint) |
| 3 | u16 | `index` |

Le récepteur **réémet l'élément tel qu'il l'a stocké** (trame
`MISSION_DEBUT`, `MISSION_LIMITES`, `ZONE_INTERDITE` ou `MISSION_WAYPOINT`
selon `element`). S'il ne l'a pas : `MISSION_ACK` avec le statut
`ID_INCONNU`, `INDEX_INVALIDE` ou `INCOMPLETE`. L'émetteur compare
**octet par octet** les données relues avec celles qu'il a envoyées : AU2
doit donc stocker les valeurs **sans perte de précision**.

---

## 7. Énumérations

### 7.1 Modes de vol (`mode_vol`)

0 `INITIALISATION`, 1 `STABILISE`, 2 `MAINTIEN_ALTITUDE`, 3 `MAINTIEN_POSITION`,
4 `MISSION`, 5 `RETOUR_MAISON`, 6 `ATTERRISSAGE`, 7 `DECOLLAGE`, 8 `URGENCE`.

### 7.2 État GPS (`etat_gps`)

0 pas de GPS, 1 pas de fix, 2 fix 2D, 3 fix 3D, 4 DGPS/SBAS, 5 RTK flottant, 6 RTK fixe.

### 7.3 Drapeaux de télémétrie (`TELEMETRIE.drapeaux`, `HEARTBEAT.etat` d'AU1 et d'AU2)

| Bit | Signification |
|---|---|
| 0 | armé |
| 1 | en vol |
| 2 | point de départ enregistré |
| 3 | mission chargée |
| 4 | failsafe actif |
| 5 | évitement d'obstacle actif |
| 6 | liaison LoRa sol OK |
| 7 | liaison AU1 ↔ AU2 OK |

Le planificateur affiche les bits 0, 1 et 3 du heartbeat d'AU2 (armé, en vol,
mission chargée).

### 7.4 Codes d'avarie (`ALERTE_AVARIE.code`)

| Code | Nom | Détecté par |
|---|---|---|
| `0x01` | *retiré, réservé* | — |
| `0x02` | `PERTE_LIAISON_LORA` | AU2 |
| `0x03` | `PERTE_LIAISON_TOURELLE` | AU2 |
| `0x04` | `BATTERIE_FAIBLE` | AU1 |
| `0x05` | `BATTERIE_CRITIQUE` | AU1 |
| `0x06` | `GPS_PERDU` | AU2 |
| `0x07` | `GEOFENCE` (limites ou zone interdite) | AU2 |
| `0x08` | `OBSTACLE` | AU2 |
| `0x09` | `DEFAUT_IMU` | AU1 |
| `0x0A` | `DEFAUT_BARO` | AU1 |
| `0x0B` | `DEFAUT_BOUSSOLE` | AU2 |
| `0x0C` | `DEFAUT_MOTEUR` | AU1 |
| `0x0D` | `PERTE_LIAISON_AU1` | AU2 |
| `0x0E` | `PERTE_LIAISON_AU2` | AU1 (⇒ atterrissage lent) |
| `0x0F` | `DEFAUT_SD` (carte SD d'AU2 : journaux impossibles) | AU2 (⇒ retour maison) |
| `0x10` | `DEFAUT_CAMERA` (absente, pas de réponse, carte pleine) | AU2 |
| `0x11` | `ARRET_URGENCE` (moteurs coupés) | AU1 |
| `0x12` | `ERREUR_LIAISON` (trames rejetées : CRC, version, NACK ; `valeur` = nombre) | AU1, AU2 |
| `0x13` | `REDEMARRAGE` (chien de garde, coupure d'alimentation) | AU1, AU2 |
| `0x40`–`0x45` | *retirés, réservés* | — |

### 7.5 Codes `NACK`

1 `FORMAT`, 2 `TYPE_INCONNU`, 3 `ETAT_INCOMPATIBLE`, 4 `HORS_LIMITES`, 5 `OCCUPE`.

### 7.6 Statuts `MISSION_ACK`

| Valeur | Nom | Sens |
|---|---|---|
| 0 | `OK` | |
| 1 | `ID_INCONNU` | `id_mission` différent de la mission en cours de chargement |
| 2 | `INDEX_INVALIDE` | index hors de `0 … nb−1` |
| 3 | `CAPACITE_DEPASSEE` | trop de waypoints, de zones ou de sommets pour la mémoire |
| 4 | `CRC_INVALIDE` | `crc_mission` différent |
| 5 | `ELEMENT_INVALIDE` | contenu incohérent (polygone de moins de 3 sommets, waypoint hors limites…) |
| 6 | `ETAT_INCOMPATIBLE` | drone armé ou en vol |
| 7 | `INCOMPLETE` | élément manquant |

### 7.8 Actions de waypoint

0 `PASSAGE`, 1 `DEBUT_PHOTOS`, 2 `FIN_PHOTOS`, 3 `PHOTO_UNIQUE`.

### 7.10 Éléments de mission (`element`)

0 `DEBUT`, 1 `LIMITES`, 2 `ZONE`, 3 `WAYPOINT`, 4 `FIN`.

---

## 8. Échanges types

### 8.1 Envoi d'un élément (avec accusé de réception)

```
émetteur ── MISSION_WAYPOINT(id, i) seq=s ──▶ récepteur
émetteur ◀── MISSION_ACK(id, WAYPOINT, i, OK) ── récepteur
```

Sans réponse au bout du délai (série : 500 ms), l'émetteur réémet
**la même trame** (même séquence), 5 fois au plus. Un statut d'erreur ou 5
échecs ⇒ abandon.

### 8.2 Transfert complet avec relecture

```
MISSION_DEBUT        ──▶  ◀── MISSION_ACK(DEBUT, 0, OK)
MISSION_LIMITES      ──▶  ◀── MISSION_ACK(LIMITES, 0, OK)
ZONE_INTERDITE(z)    ──▶  ◀── MISSION_ACK(ZONE, z, OK)          pour chaque zone
MISSION_WAYPOINT(i)  ──▶  ◀── MISSION_ACK(WAYPOINT, i, OK)      pour chaque waypoint
   ── relecture ──
MISSION_VERIFICATION(DEBUT)       ──▶  ◀── MISSION_DEBUT (tel que stocké)
MISSION_VERIFICATION(LIMITES)     ──▶  ◀── MISSION_LIMITES
MISSION_VERIFICATION(ZONE, z)     ──▶  ◀── ZONE_INTERDITE(z)
MISSION_VERIFICATION(WAYPOINT, i) ──▶  ◀── MISSION_WAYPOINT(i)
   ── comparaison octet par octet chez l'émetteur ──
MISSION_FIN(crc)     ──▶  ◀── MISSION_ACK(FIN, 0, OK)   ⇒ mission validée
```

* La relecture a lieu **avant** `MISSION_FIN` : une mission n'est jamais
  validée tant que tout n'a pas été relu identique.
* Élément relu différent : l'émetteur le renvoie puis le relit (2 fois au
  plus), sinon abandon **sans** `MISSION_FIN` (la mission reste invalide).

### 8.3 Du PC à AU2

```
PC : contrôles du planificateur (dont la culture), case « j'ai vérifié la mission » cochée
PC ══ § 8.2 sur le câble USB ══▶ AU2 (refus ETAT_INCOMPATIBLE si armé ou en vol)
PC : MISSION_FIN acquitté OK ⇒ archivage de mission_<id>.json dans data\missions
```

Il n'y a plus d'écran embarqué : la **confirmation de l'opérateur** se fait
dans le planificateur, avant l'envoi (case à cocher obligatoire, après lecture
de la carte, des calculs et des vérifications).

### 8.4 Arrêt d'urgence

```
boîtier sol ── ARRET_URGENCE(cle) seq=s   ──▶ AU2 ── ACK ──▶   (1re demande : attente 2 s)
boîtier sol ── ARRET_URGENCE(cle) seq=s+1 ──▶ AU2 ── ACK ──▶   (confirmée)
                                              AU2 ── ARRET_URGENCE ──▶ AU1 : moteurs coupés, désarmé
                                              AU2 ◀── ACK ── AU1
                                              AU2 ◀── ALERTE_AVARIE(ARRET_URGENCE) ── AU1
                                              boîte noire + LoRa vers le sol
```

---

## 9. *(section retirée, numéro conservé pour les renvois)*

---

## 10. À reporter côté Arduino

**AU2** (navigation) :

| Id | Nom | Liaison | Ce qu'AU2 doit faire |
|---|---|---|---|
| `0x01` | `HEARTBEAT` | USB, AU | émettre toutes les 500 ms ; surveiller celui d'AU1 (perte > 2 s ⇒ avarie `0x0D`) |
| `0x04` | `TEXTE` | USB | messages lisibles pour le planificateur (jamais de texte brut sur l'USB) |
| `0x11` | `ALERTE_AVARIE` | AU, LoRa | écrire chaque alerte reçue ou émise dans la boîte noire ; relayer au sol |
| `0x22`, `0x23` | `ATTERRISSAGE`, `RETOUR_MAISON` | LoRa → AU | acquitter, exécuter, journaliser |
| `0x24` | `ARRET_URGENCE` | LoRa → AU | **ajouté** : double confirmation (§ 6.3), puis ordre à AU1 |
| `0x40`–`0x46` | mission | USB | stocker sans perte, acquitter, relire, valider (§ 8.2) ; refuser si armé |

Plus : déclencher la caméra et écrire `photos.csv` et `boite_noire.csv` (§ 12).

**AU1** (pilotage) : `HEARTBEAT` (perte d'AU2 > 2 s ⇒ avarie `0x0E` et
atterrissage lent), `ALERTE_AVARIE` vers AU2 (réémise toutes les 5 s tant
qu'elle est active), `ARRET_URGENCE` (couper, désarmer, acquitter),
désarmement automatique au sol (§ 4.1).

Constantes à aligner entre le code d'AU2 et le planificateur (`config.js`) :
`max_waypoints` (150), `max_zones` (8), `max_sommets_limites` (30),
`max_sommets_zone` (16), `hauteur_max_m` (50 par défaut ; jamais plus de
120 m, plafond de la catégorie « ouverte » : mettre la hauteur de votre
autorisation), `vitesse_max` (8 m/s).
Ordre de grandeur mémoire (valeurs stockées sans perte) : limites 240 o,
zones 8 × 16 × 8 = 1 ko, waypoints 150 × 19 ≈ 2,9 ko ⇒ l'EEPROM (4 ko) ou
une SRAM externe est conseillée pour les waypoints.

L'en-tête [`arduino/ProtocoleDrone/ProtocoleDrone.h`](arduino/ProtocoleDrone/ProtocoleDrone.h)
contient tout cela (constantes, structures, CRC, décodeur, CRC de mission,
double confirmation de l'arrêt d'urgence), prêt à être utilisé dans AU1, AU2,
l'Uno et le boîtier sol ; [`FichiersVol.h`](arduino/ProtocoleDrone/FichiersVol.h)
met en forme les lignes des fichiers de la carte SD (§ 12).

---

## 11. Vecteurs de test

[`vecteurs_test.json`](vecteurs_test.json) contient des trames calculées à
l'avance par `outils/generer_vecteurs.py`. Toutes les implémentations les
vérifient :

* JavaScript : `planificateur/tests/protocole.test.mjs`
* C++ : `protocole/arduino/test_hote/test_protocole.cpp` (compilé sur PC)

Les lignes des fichiers de la carte SD sont vérifiées par
`protocole/arduino/test_hote/test_fichiers_vol.cpp` ; un vol d'exemple
conforme est dans [`exemples_fichiers/vol_exemple/`](exemples_fichiers/vol_exemple/).

---

## 12. Fichiers écrits par AU2 (contrat avec le pipeline d'analyse)

Ces fichiers sont l'**entrée du pipeline d'analyse des images**
(`src\modules\pipeline-analyse`). Leurs colonnes ne changent **jamais sans prévenir** :
une modification se fait ici, dans `FichiersVol.h`, dans
`verifier_fichiers_vol.py` et dans la notice du pipeline, en même temps.

### 12.1 Règles communes

* Carte SD **reliée directement à AU2** (SPI), bibliothèque SdFat (noms longs).
* Un dossier par vol : `/vols/mission_<id sur 5 chiffres>_<n sur 2 chiffres>/`
  (ex. `/vols/mission_00012_01/`), créé au décollage ; `n` augmente si la
  même mission vole plusieurs fois.
* Texte **UTF-8 sans BOM**, séparateur **`;`**, point décimal, fin de ligne
  `\n`, **une ligne d'en-tête** exacte.
* Chaque ligne est écrite **puis synchronisée** (`sync()`) : une coupure de
  courant ne perd que la ligne en cours.
* Carte SD absente ou en erreur : alerte `DEFAUT_SD` par LoRa (critique,
  action retour maison) — le vol n'a plus de valeur pour l'analyse.
* Après l'atterrissage, le dossier est transféré en Wi-Fi au PC avec les
  photos de la caméra (**TO DO : module Wi-Fi**) et déposé dans
  `data\vols\entrant\<nom du vol>\` : `images\`, `photos.csv`,
  `boite_noire.csv`.

### 12.2 `photos.csv` — une ligne par photo

```
fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission
IMG_0001.JPG;2026-11-02T14:05:12Z;48.3010580;1.6030366;10.00;87.5;0;12
```

| Colonne | Format | Source |
|---|---|---|
| `fichier` | nom **imposé par AU2** à la caméra : `IMG_0001.JPG`… (numéro sur 4 chiffres, à partir de 1 dans chaque vol) | AU2 |
| `horodatage_utc` | ISO 8601 UTC `AAAA-MM-JJThh:mm:ssZ`, instant du déclenchement | heure du GPS |
| `lat`, `lon` | degrés décimaux WGS84, **7 décimales** | GPS (`latitude_e7`) |
| `altitude_rel_m` | mètres au-dessus du décollage, **2 décimales** | AU2 (baromètre + GPS) |
| `cap_deg` | 0 à 359.9, nord = 0, **1 décimale** | magnétomètre d'AU2 |
| `index_waypoint` | index du **dernier waypoint atteint** (le drone est sur le tronçon `index` → `index + 1`) | mission |
| `id_mission` | `id_mission` de la mission chargée (`MISSION_DEBUT`) | mission |

Une photo n'est décrite que si toutes les colonnes sont connues : **sans
heure GPS, pas de ligne** (AU2 écrit à la place une alerte `GPS_PERDU` dans la
boîte noire). Une photo déclenchée mais non confirmée par la caméra donne une
alerte `DEFAUT_CAMERA` (TO DO : selon le modèle de caméra).

### 12.3 `boite_noire.csv` — une ligne par événement

```
horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail
2026-11-02T14:05:30Z;84400;AU1;ALERTE;0x04;BATTERIE_FAIBLE;AVERTISSEMENT;RETOUR_MAISON;142;1;14,2 V
```

| Colonne | Format |
|---|---|
| `horodatage_utc` | comme ci-dessus ; **vide** tant que le GPS n'a pas l'heure |
| `temps_ms` | `millis()` d'AU2 (toujours renseigné) |
| `source` | `AU2`, `AU1`, `TOURELLE`, `SOL`, `PC` (§ 3) |
| `categorie` | `ALERTE`, `ORDRE`, `MODE`, `MISSION`, `LIAISON`, `SYSTEME` |
| `code` | `0xHH` : code d'avarie (ALERTE), type de message (ORDRE, LIAISON), mode de vol (MODE), statut (MISSION) |
| `nom` | nom lisible (`PERTE_LIAISON_AU1`, `ARRET_URGENCE`, `MISSION_CHARGEE`…) |
| `gravite` | `INFO`, `AVERTISSEMENT`, `CRITIQUE`, `URGENCE` |
| `action` | `AUCUNE`, `MAINTIEN_POSITION`, `RETOUR_MAISON`, `ATTERRISSAGE`, `COUPURE_MOTEURS`, `POURSUITE` |
| `valeur` | entier contextuel (tension en dV, nombre de trames rejetées…) |
| `actif` | `1` apparition, `0` disparition, vide si sans objet |
| `detail` | texte libre court (les `;` sont remplacés par `,`) |

**Ce qui est écrit** (règle : toute erreur donne une ligne) :

* chaque `ALERTE_AVARIE` émise par AU2 ou reçue d'AU1 et de la tourelle,
  à l'apparition, à la disparition, et ses rappels ;
* chaque ordre reçu du sol (`ATTERRISSAGE`, `RETOUR_MAISON`,
  `ARRET_URGENCE` — première demande et exécution —, `COMMANDE_MODE`) ;
* armement, désarmement (y compris automatique), changement de mode de vol ;
* mission reçue, refusée (avec le statut), validée ; début et fin du vol ;
* trames rejetées (CRC, version, NACK) : première erreur, puis un résumé
  toutes les 10 s tant que le compteur augmente (`ERREUR_LIAISON`) ;
* démarrage, redémarrage, carte SD, caméra.
