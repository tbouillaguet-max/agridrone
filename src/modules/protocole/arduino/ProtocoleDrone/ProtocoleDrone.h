// =============================================================================
// ProtocoleDrone.h — protocole commun v1 (AU1, AU2, Uno, boîtier sol LoRa, tests PC)
//
// Référence : protocole/SPECIFICATION.md. Ce fichier ne dépend que de
// <stddef.h>, <stdint.h> et <string.h> : il compile pour AVR (Arduino) comme
// pour un PC (test sur hôte dans protocole/arduino/test_hote/).
//
// Utilisation typique sur AU2 (réception de la mission envoyée par le PC sur
// le câble USB, c'est-à-dire Serial) :
//
//   #include <ProtocoleDrone.h>
//   DecodeurTrame decodeurPc;             // un décodeur PAR liaison
//   uint16_t seqPc = 0;                   // un compteur de séquence PAR liaison
//
//   void loop() {
//     while (Serial.available()) {
//       if (decodeurPc.pousser(Serial.read(), millis())) {
//         const TrameRecue &t = decodeurPc.trame();
//         if (t.type == TYPE_MISSION_WAYPOINT) {
//           MsgMissionWaypoint wp;
//           if (decodeurPc.lire(wp)) {
//             ... stocker wp (sans perte : la relecture compare octet par octet) ...
//             MsgMissionAck ack = { wp.id_mission, ELEMENT_WAYPOINT, wp.index, MISSION_OK };
//             uint8_t tampon[TAILLE_TRAME_MAX];
//             Serial.write(tampon, encoderMessage(tampon, TYPE_MISSION_ACK, seqPc++, ack));
//           }
//         }
//       }
//     }
//   }
//
// Les structures sont « packed » : sur AVR (8 bits, little-endian) comme sur
// x86/ARM little-endian, leur image mémoire est exactement la charge utile.
// =============================================================================
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// ----------------------------------------------------------------------------
// Format de trame (§ 2)
// ----------------------------------------------------------------------------
static const uint8_t PROTO_SYNCHRO_1 = 0xAA;
static const uint8_t PROTO_SYNCHRO_2 = 0x55;
static const uint8_t PROTO_VERSION = 1;
static const uint8_t TAILLE_ENTETE = 7;  // AA 55 version type seq(2) longueur
static const uint8_t TAILLE_CRC = 2;
static const uint16_t TAILLE_TRAME_MAX = 7 + 255 + 2;
static const uint16_t DELAI_TRAME_INCOMPLETE_MS = 100;

// ----------------------------------------------------------------------------
// Types de messages (§ 5). [+] = ajouté par la spécification v1.
// ----------------------------------------------------------------------------
static const uint8_t TYPE_HEARTBEAT = 0x01;
static const uint8_t TYPE_ACK = 0x02;
static const uint8_t TYPE_NACK = 0x03;
static const uint8_t TYPE_TEXTE = 0x04;                 // [+]
static const uint8_t TYPE_TELEMETRIE = 0x10;
static const uint8_t TYPE_ALERTE_AVARIE = 0x11;
static const uint8_t TYPE_DISTANCES_TOURELLE = 0x12;
static const uint8_t TYPE_COMMANDE_MODE = 0x20;
static const uint8_t TYPE_COMMANDE_MANUELLE = 0x21;
static const uint8_t TYPE_ATTERRISSAGE = 0x22;
static const uint8_t TYPE_RETOUR_MAISON = 0x23;
static const uint8_t TYPE_ARRET_URGENCE = 0x24;         // [+] coupure des moteurs (§ 6.3)
static const uint8_t TYPE_MISSION_DEBUT = 0x40;
static const uint8_t TYPE_MISSION_LIMITES = 0x41;       // [+]
static const uint8_t TYPE_ZONE_INTERDITE = 0x42;
static const uint8_t TYPE_MISSION_WAYPOINT = 0x43;
static const uint8_t TYPE_MISSION_FIN = 0x44;
static const uint8_t TYPE_MISSION_ACK = 0x45;
static const uint8_t TYPE_MISSION_VERIFICATION = 0x46;  // [+]
// 0x30, 0x31, 0x47 et 0x50 : retirés, réservés (ne pas réutiliser, § 5).

// ----------------------------------------------------------------------------
// Identifiants d'émetteurs (§ 3)
// ----------------------------------------------------------------------------
static const uint8_t EMETTEUR_AU2 = 0x00;            // navigation, capteurs, LoRa, mission
static const uint8_t EMETTEUR_UNO = 0x01;            // tourelle ultrason
// 0x02 : retiré, réservé
static const uint8_t EMETTEUR_BOITIER_SOL = 0x03;
static const uint8_t EMETTEUR_PLANIFICATEUR = 0x04;
static const uint8_t EMETTEUR_AU1 = 0x05;            // pilotage, stabilisation, moteurs
static const uint8_t EMETTEUR_INCONNU = 0xFF;

// ----------------------------------------------------------------------------
// Énumérations (§ 7)
// ----------------------------------------------------------------------------
enum ModeVol : uint8_t {
  MODE_INITIALISATION = 0,
  MODE_STABILISE = 1,
  MODE_MAINTIEN_ALTITUDE = 2,
  MODE_MAINTIEN_POSITION = 3,
  MODE_MISSION = 4,
  MODE_RETOUR_MAISON = 5,
  MODE_ATTERRISSAGE = 6,
  MODE_DECOLLAGE = 7,
  MODE_URGENCE = 8,
};

enum EtatGps : uint8_t {
  GPS_ABSENT = 0, GPS_PAS_DE_FIX = 1, GPS_FIX_2D = 2, GPS_FIX_3D = 3,
  GPS_DGPS = 4, GPS_RTK_FLOTTANT = 5, GPS_RTK_FIXE = 6,
};

// Drapeaux de télémétrie (et HEARTBEAT.etat d'AU2 et d'AU1)
static const uint8_t DRAPEAU_ARME = 1 << 0;
static const uint8_t DRAPEAU_EN_VOL = 1 << 1;
static const uint8_t DRAPEAU_DEPART_DEFINI = 1 << 2;
static const uint8_t DRAPEAU_MISSION_CHARGEE = 1 << 3;
static const uint8_t DRAPEAU_FAILSAFE = 1 << 4;
static const uint8_t DRAPEAU_EVITEMENT = 1 << 5;
static const uint8_t DRAPEAU_LORA_OK = 1 << 6;
static const uint8_t DRAPEAU_LIAISON_AU_OK = 1 << 7;  // liaison AU1 <-> AU2 OK

enum CodeAvarie : uint8_t {
  // 0x01 : retiré, réservé
  AVARIE_PERTE_LIAISON_LORA = 0x02,
  AVARIE_PERTE_LIAISON_TOURELLE = 0x03,
  AVARIE_BATTERIE_FAIBLE = 0x04,
  AVARIE_BATTERIE_CRITIQUE = 0x05,
  AVARIE_GPS_PERDU = 0x06,
  AVARIE_GEOFENCE = 0x07,
  AVARIE_OBSTACLE = 0x08,
  AVARIE_DEFAUT_IMU = 0x09,
  AVARIE_DEFAUT_BARO = 0x0A,
  AVARIE_DEFAUT_BOUSSOLE = 0x0B,
  AVARIE_DEFAUT_MOTEUR = 0x0C,
  AVARIE_PERTE_LIAISON_AU1 = 0x0D,     // détectée par AU2
  AVARIE_PERTE_LIAISON_AU2 = 0x0E,     // détectée par AU1 => atterrissage lent
  AVARIE_DEFAUT_SD = 0x0F,             // carte SD d'AU2 (photos.csv, boîte noire)
  AVARIE_DEFAUT_CAMERA = 0x10,         // caméra absente, pas de réponse, carte pleine
  AVARIE_ARRET_URGENCE = 0x11,         // arrêt d'urgence exécuté (moteurs coupés)
  AVARIE_ERREUR_LIAISON = 0x12,        // trames rejetées (CRC, version, NACK) sur une liaison
  AVARIE_REDEMARRAGE = 0x13,           // AU1 ou AU2 a redémarré (chien de garde, coupure)
  // 0x40 à 0x45 : retirés, réservés
};

enum Gravite : uint8_t { GRAVITE_INFO = 0, GRAVITE_AVERTISSEMENT = 1, GRAVITE_CRITIQUE = 2, GRAVITE_URGENCE = 3 };

enum ActionAvarie : uint8_t {
  ACTION_AUCUNE = 0, ACTION_MAINTIEN_POSITION = 1, ACTION_RETOUR_MAISON = 2,
  ACTION_ATTERRISSAGE = 3, ACTION_COUPURE_MOTEURS = 4, ACTION_POURSUITE = 5,
};

enum CodeNack : uint8_t {
  NACK_FORMAT = 1, NACK_TYPE_INCONNU = 2, NACK_ETAT_INCOMPATIBLE = 3, NACK_HORS_LIMITES = 4, NACK_OCCUPE = 5,
};

// Statuts de MISSION_ACK (§ 7.6)
enum StatutMission : uint8_t {
  MISSION_OK = 0, MISSION_ID_INCONNU = 1, MISSION_INDEX_INVALIDE = 2,
  MISSION_CAPACITE_DEPASSEE = 3, MISSION_CRC_INVALIDE = 4,
  MISSION_ELEMENT_INVALIDE = 5, MISSION_ETAT_INCOMPATIBLE = 6, MISSION_INCOMPLETE = 7,
};

// Éléments de mission (§ 7.10)
enum ElementMission : uint8_t {
  ELEMENT_DEBUT = 0, ELEMENT_LIMITES = 1, ELEMENT_ZONE = 2, ELEMENT_WAYPOINT = 3, ELEMENT_FIN = 4,
};

static const uint8_t MISSION_OPTION_RETOUR_MAISON = 1 << 0;
static const uint8_t MISSION_OPTION_ATTERRIR = 1 << 1;

enum ActionWaypoint : uint8_t { WP_PASSAGE = 0, WP_DEBUT_PHOTOS = 1, WP_FIN_PHOTOS = 2, WP_PHOTO_UNIQUE = 3 };

// Arrêt d'urgence (§ 6.3) : clé fixe, et deux ordres distincts en moins de 2 s
static const uint16_t CLE_ARRET_URGENCE = 0x5AA5;
static const uint16_t DELAI_CONFIRMATION_ARRET_MS = 2000;

// Délais (§ 4)
static const uint16_t PERIODE_HEARTBEAT_MS = 500;
static const uint16_t DELAI_PERTE_LIAISON_MS = 2000;
static const uint16_t DELAI_DESARMEMENT_SOL_MS = 3000;  // posé et immobile => désarmement automatique

// Capacités : à aligner avec le code d'AU2 et le planificateur (config.js)
#ifndef MAX_WAYPOINTS
#define MAX_WAYPOINTS 150
#endif
#ifndef MAX_ZONES
#define MAX_ZONES 8
#endif
#ifndef MAX_SOMMETS_LIMITES
#define MAX_SOMMETS_LIMITES 30
#endif
#ifndef MAX_SOMMETS_ZONE
#define MAX_SOMMETS_ZONE 16
#endif
static const uint8_t SOMMETS_MAX_TRAME = 30;  // limite du format (255 octets de données)

// ----------------------------------------------------------------------------
// Charges utiles (§ 6). Taille vérifiée à la compilation.
// ----------------------------------------------------------------------------
#define PROTO_PACKED __attribute__((packed))

struct PROTO_PACKED MsgHeartbeat {
  uint8_t emetteur;
  uint8_t etat;
  uint32_t temps_ms;
};

struct PROTO_PACKED MsgAck {
  uint8_t type_acquitte;
  uint16_t sequence_acquittee;
};

struct PROTO_PACKED MsgNack {
  uint8_t type_refuse;
  uint16_t sequence_refusee;
  uint8_t code;
};

// TEXTE : 2 octets d'en-tête puis le texte UTF-8 (pas de structure fixe).
struct PROTO_PACKED MsgTexteEntete {
  uint8_t gravite;
  uint8_t source;
};

struct PROTO_PACKED MsgTelemetrie {
  uint32_t temps_ms;
  int16_t roulis_cdeg;
  int16_t tangage_cdeg;
  uint16_t lacet_cdeg;
  int32_t latitude_e7;
  int32_t longitude_e7;
  int32_t altitude_msl_cm;
  int32_t altitude_relative_cm;
  uint16_t vitesse_sol_cms;
  int16_t vitesse_verticale_cms;
  uint16_t route_cdeg;
  uint16_t tension_batterie_mv;
  int16_t courant_batterie_ca;
  uint8_t batterie_pct;
  uint8_t mode_vol;
  uint8_t etat_gps;
  uint8_t nb_satellites;
  uint16_t hdop_x100;
  uint8_t drapeaux;
  uint16_t waypoint_courant;
  uint16_t photos_declenchees;
};

struct PROTO_PACKED MsgAlerteAvarie {
  uint8_t code;
  uint8_t gravite;
  uint8_t source;
  uint8_t action;
  int16_t valeur;
  uint8_t actif;
};

// DISTANCES_TOURELLE : en-tête puis nb_mesures × uint16_t (contenu proposé, § 6.3)
struct PROTO_PACKED MsgDistancesTourelleEntete {
  uint8_t nb_mesures;
  int16_t angle_debut_cdeg;
  int16_t pas_cdeg;
};

struct PROTO_PACKED MsgCommandeMode {
  uint8_t mode_vol;
};

struct PROTO_PACKED MsgCommandeManuelle {
  int16_t roulis;  // -1000..1000
  int16_t tangage;
  int16_t lacet;
  int16_t gaz;
};

struct PROTO_PACKED MsgArretUrgence {
  uint16_t cle;  // toujours CLE_ARRET_URGENCE
};

struct PROTO_PACKED MsgMissionDebut {
  uint16_t id_mission;
  uint16_t nb_waypoints;
  uint8_t nb_sommets_limites;
  uint8_t nb_zones;
  uint16_t distance_photos_cm;
  uint16_t vitesse_cms;
  uint8_t options;
  uint8_t hauteur_max_m;
};

struct PROTO_PACKED Sommet {
  int32_t latitude_e7;
  int32_t longitude_e7;
};

// MISSION_LIMITES : en-tête puis nb_sommets × Sommet
struct PROTO_PACKED MsgMissionLimitesEntete {
  uint16_t id_mission;
  uint8_t nb_sommets;
};

// ZONE_INTERDITE : en-tête puis nb_sommets × Sommet
struct PROTO_PACKED MsgZoneEntete {
  uint16_t id_mission;
  uint8_t index_zone;
  uint8_t nb_sommets;
};

struct PROTO_PACKED MsgMissionWaypoint {
  uint16_t id_mission;
  uint16_t index;
  int32_t latitude_e7;
  int32_t longitude_e7;
  int32_t altitude_relative_cm;
  uint16_t vitesse_cms;
  uint8_t action;
};

struct PROTO_PACKED MsgMissionFin {
  uint16_t id_mission;
  uint16_t crc_mission;
};

struct PROTO_PACKED MsgMissionAck {
  uint16_t id_mission;
  uint8_t element;
  uint16_t index;
  uint8_t statut;
};

struct PROTO_PACKED MsgMissionVerification {
  uint16_t id_mission;
  uint8_t element;
  uint16_t index;
};


// Vérification des tailles (une erreur ici = structure différente de la spécification)
static_assert(sizeof(MsgHeartbeat) == 6, "HEARTBEAT");
static_assert(sizeof(MsgAck) == 3, "ACK");
static_assert(sizeof(MsgNack) == 4, "NACK");
static_assert(sizeof(MsgTelemetrie) == 47, "TELEMETRIE");
static_assert(sizeof(MsgAlerteAvarie) == 7, "ALERTE_AVARIE");
static_assert(sizeof(MsgDistancesTourelleEntete) == 5, "DISTANCES_TOURELLE");
static_assert(sizeof(MsgCommandeMode) == 1, "COMMANDE_MODE");
static_assert(sizeof(MsgCommandeManuelle) == 8, "COMMANDE_MANUELLE");
static_assert(sizeof(MsgArretUrgence) == 2, "ARRET_URGENCE");
static_assert(sizeof(MsgMissionDebut) == 12, "MISSION_DEBUT");
static_assert(sizeof(Sommet) == 8, "Sommet");
static_assert(sizeof(MsgMissionLimitesEntete) == 3, "MISSION_LIMITES");
static_assert(sizeof(MsgZoneEntete) == 4, "ZONE_INTERDITE");
static_assert(sizeof(MsgMissionWaypoint) == 19, "MISSION_WAYPOINT");
static_assert(sizeof(MsgMissionFin) == 4, "MISSION_FIN");
static_assert(sizeof(MsgMissionAck) == 6, "MISSION_ACK");
static_assert(sizeof(MsgMissionVerification) == 5, "MISSION_VERIFICATION");

// ----------------------------------------------------------------------------
// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF). Contrôle : "123456789" -> 0x29B1
// ----------------------------------------------------------------------------
static inline uint16_t crc16Ajouter(uint16_t crc, uint8_t octet) {
  crc ^= (uint16_t)octet << 8;
  for (uint8_t i = 0; i < 8; i++) {
    crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

static inline uint16_t crc16(const void *donnees, uint16_t n, uint16_t crc = 0xFFFF) {
  const uint8_t *d = (const uint8_t *)donnees;
  while (n--) crc = crc16Ajouter(crc, *d++);
  return crc;
}

// CRC de mission (MISSION_FIN.crc_mission, § 6.5) : partir de 0xFFFF et
// enchaîner, dans l'ordre, les DONNÉES de MISSION_DEBUT, MISSION_LIMITES,
// chaque ZONE_INTERDITE (index croissants) puis chaque MISSION_WAYPOINT.
// Pour un polygone stocké en mémoire, on enchaîne l'en-tête puis les sommets :
//   crc = crc16(&entete, sizeof entete, crc); crc = crc16(sommets, n * sizeof(Sommet), crc);

// ----------------------------------------------------------------------------
// Encodage : écrit une trame complète dans `sortie` (TAILLE_TRAME_MAX octets
// suffisent toujours) et renvoie sa taille, ou 0 si la longueur dépasse 255.
// ----------------------------------------------------------------------------
static inline size_t encoderTrame(uint8_t *sortie, uint8_t type, uint16_t sequence,
                                  const void *donnees, uint16_t longueur) {
  if (longueur > 255) return 0;
  sortie[0] = PROTO_SYNCHRO_1;
  sortie[1] = PROTO_SYNCHRO_2;
  sortie[2] = PROTO_VERSION;
  sortie[3] = type;
  sortie[4] = (uint8_t)(sequence & 0xFF);
  sortie[5] = (uint8_t)(sequence >> 8);
  sortie[6] = (uint8_t)longueur;
  if (longueur) memcpy(sortie + TAILLE_ENTETE, donnees, longueur);
  uint16_t crc = crc16(sortie + 2, (uint16_t)(5 + longueur));
  sortie[TAILLE_ENTETE + longueur] = (uint8_t)(crc & 0xFF);
  sortie[TAILLE_ENTETE + longueur + 1] = (uint8_t)(crc >> 8);
  return TAILLE_ENTETE + longueur + TAILLE_CRC;
}

template <typename T>
static inline size_t encoderMessage(uint8_t *sortie, uint8_t type, uint16_t sequence, const T &message) {
  return encoderTrame(sortie, type, sequence, &message, sizeof(T));
}

// Trame en deux morceaux (en-tête fixe + tableau), pratique pour réémettre un
// polygone stocké (relecture) : encoderTrame2(t, TYPE_MISSION_LIMITES, seq, &ent, sizeof ent, sommets, n * 8)
static inline size_t encoderTrame2(uint8_t *sortie, uint8_t type, uint16_t sequence,
                                   const void *entete, uint16_t tailleEntete,
                                   const void *suite, uint16_t tailleSuite) {
  uint16_t longueur = tailleEntete + tailleSuite;
  if (longueur > 255) return 0;
  uint8_t tampon[255];
  memcpy(tampon, entete, tailleEntete);
  if (tailleSuite) memcpy(tampon + tailleEntete, suite, tailleSuite);
  return encoderTrame(sortie, type, sequence, tampon, longueur);
}

// ----------------------------------------------------------------------------
// Décodage d'un flux d'octets (une instance par liaison)
// ----------------------------------------------------------------------------
struct TrameRecue {
  uint8_t version;
  uint8_t type;
  uint16_t sequence;
  uint8_t longueur;
  uint8_t donnees[255];
};

class DecodeurTrame {
 public:
  // Statistiques (utiles pour surveiller la qualité d'une liaison)
  uint32_t tramesValides = 0;
  uint32_t erreursCrc = 0;
  uint32_t erreursVersion = 0;
  uint32_t tramesIncompletes = 0;

  // Consomme un octet. Renvoie true quand une trame valide est disponible
  // dans trame() (valable jusqu'au prochain appel). `maintenantMs` sert à
  // abandonner une trame incomplète (passer millis() ; 0 désactive).
  bool pousser(uint8_t octet, uint32_t maintenantMs = 0) {
    if (etat_ != ATTENTE_AA && maintenantMs != 0 &&
        (uint32_t)(maintenantMs - debutMs_) > DELAI_TRAME_INCOMPLETE_MS) {
      tramesIncompletes++;
      etat_ = ATTENTE_AA;
    }
    switch (etat_) {
      case ATTENTE_AA:
        if (octet == PROTO_SYNCHRO_1) { etat_ = ATTENTE_55; debutMs_ = maintenantMs; }
        break;
      case ATTENTE_55:
        if (octet == PROTO_SYNCHRO_2) etat_ = VERSION;
        else if (octet != PROTO_SYNCHRO_1) etat_ = ATTENTE_AA;  // "AA AA 55" reste valide
        break;
      case VERSION:
        if (octet != PROTO_VERSION) { erreursVersion++; etat_ = ATTENTE_AA; break; }
        t_.version = octet; crc_ = crc16Ajouter(0xFFFF, octet); etat_ = TYPE;
        break;
      case TYPE:
        t_.type = octet; crc_ = crc16Ajouter(crc_, octet); etat_ = SEQ_L;
        break;
      case SEQ_L:
        t_.sequence = octet; crc_ = crc16Ajouter(crc_, octet); etat_ = SEQ_H;
        break;
      case SEQ_H:
        t_.sequence |= (uint16_t)octet << 8; crc_ = crc16Ajouter(crc_, octet); etat_ = LONGUEUR;
        break;
      case LONGUEUR:
        t_.longueur = octet; crc_ = crc16Ajouter(crc_, octet); index_ = 0;
        etat_ = (octet == 0) ? CRC_L : DONNEES;
        break;
      case DONNEES:
        t_.donnees[index_++] = octet; crc_ = crc16Ajouter(crc_, octet);
        if (index_ >= t_.longueur) etat_ = CRC_L;
        break;
      case CRC_L:
        crcRecu_ = octet; etat_ = CRC_H;
        break;
      case CRC_H:
        crcRecu_ |= (uint16_t)octet << 8;
        etat_ = ATTENTE_AA;
        if (crcRecu_ == crc_) { tramesValides++; return true; }
        erreursCrc++;
        break;
    }
    return false;
  }

  const TrameRecue &trame() const { return t_; }

  // Copie la charge utile dans une structure si la longueur suffit.
  template <typename T>
  bool lire(T &sortie) const {
    if (t_.longueur < sizeof(T)) return false;
    memcpy(&sortie, t_.donnees, sizeof(T));
    return true;
  }

 private:
  enum Etat : uint8_t { ATTENTE_AA, ATTENTE_55, VERSION, TYPE, SEQ_L, SEQ_H, LONGUEUR, DONNEES, CRC_L, CRC_H };
  Etat etat_ = ATTENTE_AA;
  TrameRecue t_;
  uint16_t crc_ = 0xFFFF;
  uint16_t crcRecu_ = 0;
  uint16_t index_ = 0;
  uint32_t debutMs_ = 0;
};

// ----------------------------------------------------------------------------
// Détection des doublons de commandes (réémissions, § 2.3) :
// mémorise les derniers (type, séquence) reçus.
// ----------------------------------------------------------------------------
class FiltreDoublons {
 public:
  // Renvoie true si (type, sequence) a déjà été vu il y a moins de 3 s.
  bool estDoublon(uint8_t type, uint16_t sequence, uint32_t maintenantMs) {
    for (uint8_t i = 0; i < TAILLE; i++) {
      Entree &e = entrees_[i];
      if (e.valide && e.type == type && e.sequence == sequence &&
          (uint32_t)(maintenantMs - e.instantMs) < 3000UL) {
        return true;
      }
    }
    Entree &e = entrees_[prochain_];
    e.valide = true; e.type = type; e.sequence = sequence; e.instantMs = maintenantMs;
    prochain_ = (uint8_t)((prochain_ + 1) % TAILLE);
    return false;
  }

 private:
  struct Entree { bool valide; uint8_t type; uint16_t sequence; uint32_t instantMs; };
  static const uint8_t TAILLE = 8;
  Entree entrees_[TAILLE] = {};
  uint8_t prochain_ = 0;
};

// ----------------------------------------------------------------------------
// Arrêt d'urgence (§ 6.3) : AU2 ne coupe les moteurs (ordre transmis à AU1)
// qu'après DEUX trames ARRET_URGENCE valides, de numéros de séquence
// différents, reçues en moins de 2 s. Une réémission (même séquence) ne
// confirme pas. Sur la liaison AU2 -> AU1, une seule trame suffit.
// ----------------------------------------------------------------------------
class ConfirmationArretUrgence {
 public:
  // Renvoie true quand l'arrêt doit être exécuté maintenant.
  bool recevoir(const MsgArretUrgence &m, uint16_t sequence, uint32_t maintenantMs) {
    if (m.cle != CLE_ARRET_URGENCE) return false;
    if (enAttente_ && sequence != sequence_ &&
        (uint32_t)(maintenantMs - instantMs_) <= DELAI_CONFIRMATION_ARRET_MS) {
      enAttente_ = false;
      return true;
    }
    enAttente_ = true;
    sequence_ = sequence;
    instantMs_ = maintenantMs;
    return false;
  }

  // Une première demande attend sa confirmation (pour la boîte noire et la LoRa).
  bool enAttente(uint32_t maintenantMs) const {
    return enAttente_ && (uint32_t)(maintenantMs - instantMs_) <= DELAI_CONFIRMATION_ARRET_MS;
  }

 private:
  bool enAttente_ = false;
  uint16_t sequence_ = 0;
  uint32_t instantMs_ = 0;
};
