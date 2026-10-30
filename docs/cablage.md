# Câblage : PC ↔ AU2, AU2 ↔ AU1, carte SD

## 1. Schéma

```
 PC (Chrome)           câble USB A-B                 AU2 (Arduino Mega 2560)                    AU1 (Arduino Mega 2560)
 ┌──────────┐ ════════════════════════════════▶ ┌──────────────────────────┐                ┌────────────────────┐
 │ planifi- │   (port USB de la Mega = Serial)  │ TX1 (18) ───────────────────────────────▶ RX1 (19)           │
 │ cateur   │                                   │ RX1 (19) ◀─────────────────────────────── TX1 (18)           │
 └──────────┘                                   │ GND ──────────────────────────────────── GND               │
                                                │                          │                │ ESC, IMU…          │
                                                │ 50 MISO ── MISO ┐        │                └────────────────────┘
                                                │ 51 MOSI ── MOSI │ lecteur│
                                                │ 52 SCK  ── SCK  │ SD SPI │
                                                │ 53 CS   ── CS   │        │
                                                │ 5V, GND ── VCC, GND ┘    │
                                                └──────────────────────────┘
```

* **PC ↔ AU2** : le câble USB de la Mega, **au sol uniquement** (chargement de
  la mission). Ouvrir le port redémarre la Mega (DTR) : le planificateur
  attend 2 s. Fermer le moniteur série de l'IDE Arduino avant de connecter le
  planificateur (un port ne s'ouvre qu'une fois).
* **AU2 ↔ AU1** : `Serial1` des deux cartes, **croisée** (TX1 → RX1), **masse
  commune obligatoire**. Les deux Mega sont en 5 V : aucune adaptation de
  niveau. Ne pas relier les 5 V des deux cartes si elles ont des alimentations
  distinctes.
* **Carte SD** sur AU2 : bus SPI de la Mega (50 à 53). Prendre un module
  avec régulateur 3,3 V et adaptation de niveaux (la carte SD est en 3,3 V et
  la Mega en 5 V). Broche CS : 53 (à garder en sortie même si un autre CS est
  choisi).

Liaisons série : **115 200 bauds, 8 bits, sans parité, 1 bit de stop (8N1)**,
sans contrôle de flux.

| Port | Broches (RX / TX) | AU2 | AU1 |
|---|---|---|---|
| `Serial` | 0 / 1 (et le connecteur USB) | **PC** (mission, au sol) ; téléversement | téléversement, moniteur série |
| **`Serial1`** | **19 / 18** | **AU1** | **AU2** |
| `Serial2` | 17 / 16 | GPS ou LoRa (à fixer) | libre |
| `Serial3` | 15 / 14 | GPS ou LoRa (à fixer) | libre |

Caméra et module Wi-Fi : **TO DO** (dépendent des modèles choisis).

## 2. Montage sur le drone

* **Fils courts** (10 à 20 cm), torsadés (TX, RX et GND ensemble), éloignés
  des fils des moteurs et des contrôleurs (ESC) ; une ferrite si des erreurs
  CRC apparaissent moteurs tournants (elles sont écrites dans la boîte noire,
  alerte `ERREUR_LIAISON`).
* **Connecteurs immobilisés** (colle chaude, gaine thermorétractable,
  serre-câble) : les vibrations finissent par desserrer un connecteur Dupont.
* **Carte SD** bien tenue dans son support : une carte qui saute en vol
  déclenche `DEFAUT_SD` et le retour maison.
* **Caméra** au nadir. Si le grand côté de l'image est dans l'axe du drone,
  décocher « grand côté de la photo perpendiculaire aux passes » dans le
  planificateur (`grandCoteTransversal` dans `js/config.js`).
* **Interrupteur d'arrêt** accessible sur le drone : coupe les moteurs et
  interdit l'armement pendant les manipulations au sol.

## 3. Vérifier le câblage pas à pas

1. **PC ↔ AU2** : téléverser `protocole/arduino/exemples/banc_au2_mission`
   dans AU2, lancer le planificateur, *Connecter AU2 (câble USB)* : le journal
   affiche « AU2 (banc) prêt » et la ligne d'état « Drone désarmé ».
2. Relier la broche 22 d'AU2 à GND (drone « armé ») : l'état passe à
   « ARMÉ » et un envoi de mission est refusé. Relâcher : la mission passe.
3. **AU2 ↔ AU1** : téléverser `tp2_trames` dans AU2 et un croquis qui émet
   un `HEARTBEAT` (émetteur `0x05`) toutes les 500 ms dans AU1 ; le moniteur
   série d'AU2 liste les trames d'AU1. Débrancher AU1 : « PERTE AU1 » après 2 s.
4. **Carte SD** : téléverser `au2_journal_vol` : le moniteur affiche les
   lignes écrites ; lire la carte sur le PC et la contrôler avec
   `python protocole/outils/verifier_fichiers_vol.py <dossier du vol>`.
