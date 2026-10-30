// Test sur PC de ProtocoleDrone.h contre les vecteurs partagés.
//   make -C protocole/arduino/test_hote
// Le même en-tête est utilisé tel quel sur AU1 et AU2 : si ce test passe, le
// codage et le décodage Arduino sont conformes à la spécification.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "../ProtocoleDrone/ProtocoleDrone.h"
#include "vecteurs_test.h"

static int echecs = 0;

#define VERIFIER(cond)                                                     \
  do {                                                                     \
    if (!(cond)) {                                                         \
      std::printf("ÉCHEC %s:%d : %s\n", __FILE__, __LINE__, #cond);         \
      echecs++;                                                            \
    }                                                                      \
  } while (0)

static std::vector<uint8_t> depuisHex(const char *hex) {
  std::vector<uint8_t> octets;
  for (size_t i = 0; hex[i] && hex[i + 1]; i += 2) {
    char paire[3] = {hex[i], hex[i + 1], 0};
    octets.push_back((uint8_t)std::strtoul(paire, nullptr, 16));
  }
  return octets;
}

static std::vector<uint8_t> trameVecteur(const char *nom) {
  for (unsigned i = 0; i < NB_VECTEURS_TRAMES; i++)
    if (std::strcmp(VECTEURS_TRAMES[i].nom, nom) == 0) return depuisHex(VECTEURS_TRAMES[i].hex);
  std::printf("vecteur introuvable : %s\n", nom);
  std::exit(2);
}

// Décode une trame complète avec le décodeur de flux.
static bool decoder(const std::vector<uint8_t> &octets, TrameRecue &sortie) {
  DecodeurTrame d;
  bool trouve = false;
  for (uint8_t o : octets) {
    if (d.pousser(o)) { sortie = d.trame(); trouve = true; }
  }
  return trouve;
}

static bool egal(const uint8_t *a, size_t n, const std::vector<uint8_t> &b) {
  return n == b.size() && std::memcmp(a, b.data(), n) == 0;
}

int main() {
  // 1. CRC
  VERIFIER(crc16("123456789", 9) == 0x29B1);

  // 2. Chaque vecteur : décodage puis ré-encodage à l'identique
  for (unsigned i = 0; i < NB_VECTEURS_TRAMES; i++) {
    std::vector<uint8_t> attendu = depuisHex(VECTEURS_TRAMES[i].hex);
    TrameRecue t;
    if (!decoder(attendu, t)) { std::printf("ÉCHEC décodage %s\n", VECTEURS_TRAMES[i].nom); echecs++; continue; }
    uint8_t tampon[TAILLE_TRAME_MAX];
    size_t n = encoderTrame(tampon, t.type, t.sequence, t.donnees, t.longueur);
    if (!egal(tampon, n, attendu)) { std::printf("ÉCHEC ré-encodage %s\n", VECTEURS_TRAMES[i].nom); echecs++; }
  }

  // 3. Lecture des structures : quelques champs
  {
    TrameRecue t;
    VERIFIER(decoder(trameVecteur("telemetrie"), t));
    MsgTelemetrie m;
    std::memcpy(&m, t.donnees, sizeof m);
    VERIFIER(t.type == TYPE_TELEMETRIE && t.sequence == 42 && t.longueur == 47);
    VERIFIER(m.roulis_cdeg == -1234 && m.lacet_cdeg == 35999 && m.latitude_e7 == 488566100);
    VERIFIER(m.vitesse_verticale_cms == -25 && m.mode_vol == MODE_MISSION && m.drapeaux == 0x4F);
  }
  {
    TrameRecue t;
    VERIFIER(decoder(trameVecteur("mission_debut"), t));
    MsgMissionDebut d;
    std::memcpy(&d, t.donnees, sizeof d);
    VERIFIER(d.id_mission == 12 && d.nb_waypoints == 4 && d.nb_sommets_limites == 4 && d.nb_zones == 1);
    VERIFIER(d.distance_photos_cm == 180 && d.options == MISSION_OPTION_RETOUR_MAISON && d.hauteur_max_m == 30);
  }
  {
    // Polygone : en-tête + sommets
    TrameRecue t;
    VERIFIER(decoder(trameVecteur("zone_interdite"), t));
    MsgZoneEntete e;
    std::memcpy(&e, t.donnees, sizeof e);
    VERIFIER(e.id_mission == 12 && e.index_zone == 0 && e.nb_sommets == 3);
    VERIFIER(t.longueur == sizeof(MsgZoneEntete) + e.nb_sommets * sizeof(Sommet));
    Sommet s[3];
    std::memcpy(s, t.donnees + sizeof e, sizeof s);
    VERIFIER(s[2].latitude_e7 == 488566000 && s[2].longitude_e7 == 23521000);
    // Réémission pour la relecture, en deux morceaux comme depuis la mémoire
    uint8_t tampon[TAILLE_TRAME_MAX];
    size_t n = encoderTrame2(tampon, TYPE_ZONE_INTERDITE, 9, &e, sizeof e, s, sizeof s);
    VERIFIER(egal(tampon, n, trameVecteur("zone_interdite")));
  }
  {
    // Encodage d'une structure -> vecteur
    MsgMissionAck a = {12, ELEMENT_WAYPOINT, 2, MISSION_OK};
    uint8_t tampon[TAILLE_TRAME_MAX];
    VERIFIER(egal(tampon, encoderMessage(tampon, TYPE_MISSION_ACK, 77, a), trameVecteur("mission_ack")));
    MsgCommandeManuelle c = {-1000, 500, 0, 1000};
    VERIFIER(egal(tampon, encoderMessage(tampon, TYPE_COMMANDE_MANUELLE, 12, c), trameVecteur("commande_manuelle")));
    VERIFIER(egal(tampon, encoderTrame(tampon, TYPE_RETOUR_MAISON, 6, nullptr, 0), trameVecteur("retour_maison")));
  }
  {
    // Arrêt d'urgence : structure, puis confirmation par deux ordres distincts en moins de 2 s
    TrameRecue t;
    VERIFIER(decoder(trameVecteur("arret_urgence"), t));
    MsgArretUrgence a;
    std::memcpy(&a, t.donnees, sizeof a);
    VERIFIER(t.type == TYPE_ARRET_URGENCE && t.longueur == 2 && a.cle == CLE_ARRET_URGENCE);
    uint8_t tampon[TAILLE_TRAME_MAX];
    VERIFIER(egal(tampon, encoderMessage(tampon, TYPE_ARRET_URGENCE, 7, a), trameVecteur("arret_urgence")));

    ConfirmationArretUrgence c;
    VERIFIER(!c.recevoir(a, 7, 10000));        // première demande : attente
    VERIFIER(c.enAttente(10500));
    VERIFIER(!c.recevoir(a, 7, 10500));        // réémission (même séquence) : pas de confirmation
    VERIFIER(c.recevoir(a, 8, 11000));         // deuxième ordre distinct à temps : arrêt
    VERIFIER(!c.enAttente(11000));
    VERIFIER(!c.recevoir(a, 9, 20000));        // nouvelle demande
    VERIFIER(!c.recevoir(a, 10, 22500));       // 2,5 s plus tard : trop tard, redevient une première demande
    VERIFIER(c.recevoir(a, 11, 23000));
    MsgArretUrgence mauvaise = {0x1234};
    ConfirmationArretUrgence c2;
    VERIFIER(!c2.recevoir(mauvaise, 1, 0) && !c2.recevoir(mauvaise, 2, 100));  // mauvaise clé : ignorée
  }
  {
    // Alerte d'AU1 : perte de la liaison avec AU2 => atterrissage
    TrameRecue t;
    VERIFIER(decoder(trameVecteur("alerte_perte_au2"), t));
    MsgAlerteAvarie a;
    std::memcpy(&a, t.donnees, sizeof a);
    VERIFIER(a.code == AVARIE_PERTE_LIAISON_AU2 && a.source == EMETTEUR_AU1 && a.action == ACTION_ATTERRISSAGE);
  }

  // 4. CRC de mission : données de DEBUT, LIMITES, ZONES, WAYPOINTS dans l'ordre
  {
    const char *ordre[] = {"mission_debut", "mission_limites", "zone_interdite", "mission_waypoint_0",
                           "mission_waypoint_1", "mission_waypoint_2", "mission_waypoint_3"};
    uint16_t crc = 0xFFFF;
    for (const char *nom : ordre) {
      TrameRecue t;
      VERIFIER(decoder(trameVecteur(nom), t));
      crc = crc16(t.donnees, t.longueur, crc);
    }
    VERIFIER(crc == CRC_MISSION_ATTENDU);
    TrameRecue fin;
    VERIFIER(decoder(trameVecteur("mission_fin"), fin));
    MsgMissionFin f;
    std::memcpy(&f, fin.donnees, sizeof f);
    VERIFIER(f.crc_mission == CRC_MISSION_ATTENDU);
  }

  // 5. Flux avec bruit et trame corrompue
  {
    std::vector<uint8_t> flux = depuisHex(FLUX_HEX);
    DecodeurTrame d;
    std::vector<uint8_t> types;
    for (uint8_t o : flux)
      if (d.pousser(o)) types.push_back(d.trame().type);
    VERIFIER(types.size() == 2 && types[0] == TYPE_HEARTBEAT && types[1] == TYPE_ACK);
    VERIFIER(d.erreursCrc == 1);
  }

  // 6. Trame incomplète abandonnée après 100 ms
  {
    std::vector<uint8_t> t = trameVecteur("heartbeat_au1");
    DecodeurTrame d;
    for (size_t i = 0; i < 5; i++) d.pousser(t[i], 1000);
    bool ok = false;
    for (uint8_t o : t) ok = d.pousser(o, 1500) || ok;  // 500 ms plus tard
    VERIFIER(ok);
    VERIFIER(d.tramesIncompletes == 1);
  }

  // 7. Filtre de doublons
  {
    FiltreDoublons f;
    VERIFIER(!f.estDoublon(TYPE_COMMANDE_MODE, 17, 1000));
    VERIFIER(f.estDoublon(TYPE_COMMANDE_MODE, 17, 2000));
    VERIFIER(!f.estDoublon(TYPE_COMMANDE_MODE, 18, 2000));
    VERIFIER(!f.estDoublon(TYPE_COMMANDE_MODE, 17, 6000));  // plus de 3 s : nouvelle commande
  }

  if (echecs == 0) {
    std::printf("OK : %u vecteurs de trames, structures, CRC de mission, flux, doublons.\n", NB_VECTEURS_TRAMES);
    return 0;
  }
  std::printf("%d échec(s)\n", echecs);
  return 1;
}
