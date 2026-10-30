// =============================================================================
// Banc d'essai « AU2 » : réception de la mission envoyée par le planificateur
//
// Ce n'est PAS le programme de vol : c'est un AU2 minimal, au sol, qui
// respecte le protocole vis-à-vis du PC (SPECIFICATION.md § 6.5, 8.2, 8.3)
// pour essayer le planificateur avec la vraie carte, par le câble USB :
//
//  - HEARTBEAT 500 ms (drapeaux ARMÉ et MISSION_CHARGEE) ;
//  - réception d'une mission : stockage SANS PERTE en RAM, MISSION_ACK pour
//    chaque élément, réponse aux MISSION_VERIFICATION (relecture), contrôle
//    du CRC à MISSION_FIN ;
//  - refus d'une nouvelle mission tant que le drone est « armé » (broche 22
//    reliée à GND) ; dès que la broche est relâchée (désarmement, comme
//    après l'atterrissage), une nouvelle mission est acceptée ;
//  - ARRET_URGENCE (§ 6.3) : deux ordres distincts en moins de 2 s coupent
//    les moteurs (ici : simulé, le drone est désarmé) ;
//  - messages lisibles envoyés en trames TEXTE (affichées dans le journal
//    du planificateur).
//
// Montage : câble USB de la Mega vers le PC ; le planificateur se connecte
// par « Connecter AU2 (câble USB) » (115 200 bauds). Pas de moniteur série :
// le port USB transporte les trames du protocole.
//
// Mémoire : 150 waypoints × 19 o + 8 zones × 16 × 8 o + 30 × 8 o ≈ 4,1 ko de
// RAM sur 8 ko : ça tient sur la Mega pour un banc d'essai. Le programme de
// vol stockera plutôt les waypoints en EEPROM (§ 10).
// =============================================================================
#include <ProtocoleDrone.h>

#define LIAISON Serial                   // câble USB vers le PC
const unsigned long DEBIT = 115200;
const uint8_t BROCHE_ARME = 22;          // reliée à GND = drone armé

// --- mission en mémoire (exactement ce qui a été reçu) ----------------------------
struct Mission {
  bool debutRecu;
  MsgMissionDebut debut;
  bool limitesRecues;
  Sommet limites[MAX_SOMMETS_LIMITES];
  uint8_t nbZonesRecues;                         // nombre de zones distinctes reçues
  bool zoneRecue[MAX_ZONES];
  uint8_t nbSommetsZone[MAX_ZONES];
  Sommet zones[MAX_ZONES][MAX_SOMMETS_ZONE];
  uint16_t nbWaypointsRecus;
  uint8_t waypointRecu[(MAX_WAYPOINTS + 7) / 8]; // un bit par waypoint
  MsgMissionWaypoint waypoints[MAX_WAYPOINTS];
  bool validee;                                  // CRC vérifié à MISSION_FIN
};
Mission mission;

DecodeurTrame decodeur;
uint16_t sequence = 0;
uint8_t tampon[TAILLE_TRAME_MAX];

uint32_t prochainHeartbeat = 0;
bool etaitArme = false;
ConfirmationArretUrgence arretUrgence;
bool moteursCoupes = false;

// --- outils ---------------------------------------------------------------------
bool arme() { return !moteursCoupes && digitalRead(BROCHE_ARME) == LOW; }

template <typename T>
void envoyer(uint8_t type, const T &message) {
  LIAISON.write(tampon, encoderMessage(tampon, type, sequence++, message));
}

// Message lisible pour le journal du planificateur (trame TEXTE, § 6.1) :
// sur ce câble, tout ce qui part vers le PC est une trame, jamais du texte brut.
void texte(uint8_t gravite, const char *t) {
  uint8_t d[2 + 120];
  d[0] = gravite;
  d[1] = EMETTEUR_AU2;
  size_t n = strlen(t);
  if (n > 120) n = 120;
  memcpy(d + 2, t, n);
  LIAISON.write(tampon, encoderTrame(tampon, TYPE_TEXTE, sequence++, d, (uint16_t)(2 + n)));
}

void ack(uint16_t id, uint8_t element, uint16_t index, uint8_t statut) {
  MsgMissionAck a = { id, element, index, statut };
  envoyer(TYPE_MISSION_ACK, a);
  // Sur le vrai AU2, chaque refus est aussi écrit dans la boîte noire (catégorie MISSION).
}

void effacerMission() { memset(&mission, 0, sizeof mission); }

bool waypointPresent(uint16_t i) { return mission.waypointRecu[i / 8] & (1 << (i % 8)); }

// --- réception des éléments (§ 6.5) --------------------------------------------------
void recevoirDebut() {
  MsgMissionDebut d;
  if (!decodeur.lire(d)) return;
  uint8_t statut = MISSION_OK;
  if (arme()) statut = MISSION_ETAT_INCOMPATIBLE;
  else if (d.nb_waypoints > MAX_WAYPOINTS || d.nb_zones > MAX_ZONES || d.nb_sommets_limites > MAX_SOMMETS_LIMITES)
    statut = MISSION_CAPACITE_DEPASSEE;
  else if (d.nb_waypoints == 0 || d.nb_sommets_limites < 3) statut = MISSION_ELEMENT_INVALIDE;
  if (statut == MISSION_OK) {
    effacerMission();            // une nouvelle mission invalide la précédente
    mission.debut = d;
    mission.debutRecu = true;
    texte(1, "AU2 (banc) : réception d'une nouvelle mission");
  } else if (statut == MISSION_ETAT_INCOMPATIBLE) {
    texte(2, "AU2 (banc) : mission refusée, drone armé (attendre l'atterrissage et le désarmement)");
  }
  ack(d.id_mission, ELEMENT_DEBUT, 0, statut);
}

void recevoirLimites(const TrameRecue &t) {
  MsgMissionLimitesEntete e;
  if (!decodeur.lire(e)) return;
  uint8_t statut = MISSION_OK;
  if (!mission.debutRecu || e.id_mission != mission.debut.id_mission) statut = MISSION_ID_INCONNU;
  else if (e.nb_sommets != mission.debut.nb_sommets_limites || t.longueur != sizeof e + e.nb_sommets * sizeof(Sommet))
    statut = MISSION_ELEMENT_INVALIDE;
  if (statut == MISSION_OK) {
    memcpy(mission.limites, t.donnees + sizeof e, e.nb_sommets * sizeof(Sommet));
    mission.limitesRecues = true;
  }
  ack(e.id_mission, ELEMENT_LIMITES, 0, statut);
}

void recevoirZone(const TrameRecue &t) {
  MsgZoneEntete e;
  if (!decodeur.lire(e)) return;
  uint8_t statut = MISSION_OK;
  if (!mission.debutRecu || e.id_mission != mission.debut.id_mission) statut = MISSION_ID_INCONNU;
  else if (e.index_zone >= mission.debut.nb_zones) statut = MISSION_INDEX_INVALIDE;
  else if (e.nb_sommets > MAX_SOMMETS_ZONE) statut = MISSION_CAPACITE_DEPASSEE;
  else if (e.nb_sommets < 3 || t.longueur != sizeof e + e.nb_sommets * sizeof(Sommet)) statut = MISSION_ELEMENT_INVALIDE;
  if (statut == MISSION_OK) {
    memcpy(mission.zones[e.index_zone], t.donnees + sizeof e, e.nb_sommets * sizeof(Sommet));
    mission.nbSommetsZone[e.index_zone] = e.nb_sommets;
    if (!mission.zoneRecue[e.index_zone]) mission.nbZonesRecues++;
    mission.zoneRecue[e.index_zone] = true;
  }
  ack(e.id_mission, ELEMENT_ZONE, e.index_zone, statut);
}

void recevoirWaypoint() {
  MsgMissionWaypoint w;
  if (!decodeur.lire(w)) return;
  uint8_t statut = MISSION_OK;
  if (!mission.debutRecu || w.id_mission != mission.debut.id_mission) statut = MISSION_ID_INCONNU;
  else if (w.index >= mission.debut.nb_waypoints) statut = MISSION_INDEX_INVALIDE;
  if (statut == MISSION_OK) {
    mission.waypoints[w.index] = w;
    if (!waypointPresent(w.index)) mission.nbWaypointsRecus++;
    mission.waypointRecu[w.index / 8] |= 1 << (w.index % 8);
  }
  ack(w.id_mission, ELEMENT_WAYPOINT, w.index, statut);
}

// Relecture : réémet l'élément tel qu'il est stocké (le PC compare octet par octet)
void relire() {
  MsgMissionVerification v;
  if (!decodeur.lire(v)) return;
  if (!mission.debutRecu || v.id_mission != mission.debut.id_mission) { ack(v.id_mission, v.element, v.index, MISSION_ID_INCONNU); return; }
  const MsgMissionDebut &d = mission.debut;
  switch (v.element) {
    case ELEMENT_DEBUT:
      envoyer(TYPE_MISSION_DEBUT, d);
      return;
    case ELEMENT_LIMITES:
      if (!mission.limitesRecues) break;
      {
        MsgMissionLimitesEntete e = { d.id_mission, d.nb_sommets_limites };
        LIAISON.write(tampon, encoderTrame2(tampon, TYPE_MISSION_LIMITES, sequence++, &e, sizeof e,
                                            mission.limites, e.nb_sommets * sizeof(Sommet)));
      }
      return;
    case ELEMENT_ZONE:
      if (v.index >= d.nb_zones) { ack(v.id_mission, v.element, v.index, MISSION_INDEX_INVALIDE); return; }
      if (!mission.zoneRecue[v.index]) break;
      {
        MsgZoneEntete e = { d.id_mission, (uint8_t)v.index, mission.nbSommetsZone[v.index] };
        LIAISON.write(tampon, encoderTrame2(tampon, TYPE_ZONE_INTERDITE, sequence++, &e, sizeof e,
                                            mission.zones[v.index], e.nb_sommets * sizeof(Sommet)));
      }
      return;
    case ELEMENT_WAYPOINT:
      if (v.index >= d.nb_waypoints) { ack(v.id_mission, v.element, v.index, MISSION_INDEX_INVALIDE); return; }
      if (!waypointPresent(v.index)) break;
      envoyer(TYPE_MISSION_WAYPOINT, mission.waypoints[v.index]);
      return;
    default:
      ack(v.id_mission, v.element, v.index, MISSION_INDEX_INVALIDE);
      return;
  }
  ack(v.id_mission, v.element, v.index, MISSION_INCOMPLETE);  // élément demandé pas encore reçu
}

// CRC de mission : données de chaque élément, dans l'ordre (§ 6.5)
uint16_t crcMission() {
  const MsgMissionDebut &d = mission.debut;
  uint16_t crc = crc16(&d, sizeof d);
  MsgMissionLimitesEntete el = { d.id_mission, d.nb_sommets_limites };
  crc = crc16(&el, sizeof el, crc);
  crc = crc16(mission.limites, el.nb_sommets * sizeof(Sommet), crc);
  for (uint8_t z = 0; z < d.nb_zones; z++) {
    MsgZoneEntete ez = { d.id_mission, z, mission.nbSommetsZone[z] };
    crc = crc16(&ez, sizeof ez, crc);
    crc = crc16(mission.zones[z], ez.nb_sommets * sizeof(Sommet), crc);
  }
  for (uint16_t i = 0; i < d.nb_waypoints; i++) crc = crc16(&mission.waypoints[i], sizeof(MsgMissionWaypoint), crc);
  return crc;
}

void recevoirFin() {
  MsgMissionFin f;
  if (!decodeur.lire(f)) return;
  const MsgMissionDebut &d = mission.debut;
  uint8_t statut = MISSION_OK;
  if (!mission.debutRecu || f.id_mission != d.id_mission) statut = MISSION_ID_INCONNU;
  else if (!mission.limitesRecues || mission.nbZonesRecues != d.nb_zones || mission.nbWaypointsRecus != d.nb_waypoints)
    statut = MISSION_INCOMPLETE;
  else if (crcMission() != f.crc_mission) statut = MISSION_CRC_INVALIDE;
  mission.validee = (statut == MISSION_OK);
  ack(f.id_mission, ELEMENT_FIN, 0, statut);
  if (mission.validee) texte(1, "AU2 (banc) : mission validée (CRC correct), prête à voler");
}

// --- arrêt d'urgence (§ 6.3) -------------------------------------------------------
void recevoirArretUrgence(const TrameRecue &t) {
  MsgArretUrgence a;
  if (!decodeur.lire(a) || a.cle != CLE_ARRET_URGENCE) {
    MsgNack n = { t.type, t.sequence, NACK_FORMAT };
    envoyer(TYPE_NACK, n);
    return;
  }
  MsgAck ok = { t.type, t.sequence };
  envoyer(TYPE_ACK, ok);
  if (arretUrgence.recevoir(a, t.sequence, millis())) {
    moteursCoupes = true;  // AU2 transmet l'ordre à AU1, qui coupe les moteurs et désarme
    MsgAlerteAvarie al = { AVARIE_ARRET_URGENCE, GRAVITE_URGENCE, EMETTEUR_AU2, ACTION_COUPURE_MOTEURS, 0, 1 };
    envoyer(TYPE_ALERTE_AVARIE, al);
    texte(3, "AU2 (banc) : ARRÊT D'URGENCE confirmé, moteurs coupés (simulé)");
  } else {
    texte(2, "AU2 (banc) : arrêt d'urgence demandé, en attente de confirmation (2 s)");
  }
}

// --- aiguillage ---------------------------------------------------------------------
void traiterTrame(const TrameRecue &t) {
  switch (t.type) {
    case TYPE_MISSION_DEBUT: recevoirDebut(); break;
    case TYPE_MISSION_LIMITES: recevoirLimites(t); break;
    case TYPE_ZONE_INTERDITE: recevoirZone(t); break;
    case TYPE_MISSION_WAYPOINT: recevoirWaypoint(); break;
    case TYPE_MISSION_VERIFICATION: relire(); break;
    case TYPE_MISSION_FIN: recevoirFin(); break;
    case TYPE_ARRET_URGENCE: recevoirArretUrgence(t); break;
    case TYPE_HEARTBEAT:
    case TYPE_TEXTE:
      break;
    default: {
      MsgNack n = { t.type, t.sequence, NACK_TYPE_INCONNU };
      envoyer(TYPE_NACK, n);
    }
  }
}

// --- programme ----------------------------------------------------------------------
void setup() {
  LIAISON.begin(DEBIT);
  pinMode(BROCHE_ARME, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  effacerMission();
  texte(1, "AU2 (banc) prêt");
}

void loop() {
  uint32_t maintenant = millis();

  while (LIAISON.available()) {
    if (decodeur.pousser(LIAISON.read(), maintenant)) traiterTrame(decodeur.trame());
  }

  // Désarmement (broche relâchée) : une nouvelle mission peut être chargée.
  bool estArme = arme();
  if (estArme != etaitArme) {
    etaitArme = estArme;
    texte(1, estArme ? "AU2 (banc) : armé, toute nouvelle mission est refusée"
                     : "AU2 (banc) : désarmé, une nouvelle mission peut être chargée");
  }
  if (digitalRead(BROCHE_ARME) == HIGH) moteursCoupes = false;  // réarmement possible après l'arrêt
  digitalWrite(LED_BUILTIN, mission.validee ? HIGH : LOW);

  if ((int32_t)(maintenant - prochainHeartbeat) >= 0) {
    uint8_t etat = DRAPEAU_DEPART_DEFINI;
    if (estArme) etat |= DRAPEAU_ARME;
    if (mission.validee) etat |= DRAPEAU_MISSION_CHARGEE;
    MsgHeartbeat hb = { EMETTEUR_AU2, etat, maintenant };
    envoyer(TYPE_HEARTBEAT, hb);
    prochainHeartbeat = maintenant + PERIODE_HEARTBEAT_MS;
  }
}
