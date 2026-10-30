// Généré par protocole/outils/generer_vecteurs.py — ne pas modifier à la main.
#pragma once
#include <stdint.h>

struct VecteurTrame { const char *nom; const char *hex; };
static const VecteurTrame VECTEURS_TRAMES[] = {
  {"heartbeat_au1", "aa550101010006050340e201002a17"},
  {"heartbeat_au2", "aa550101020006004d06120f00f72e"},
  {"ack_arret_urgence", "aa5501022c01032411002c73"},
  {"nack_etat", "aa5501032d0104401200038200"},
  {"telemetrie", "aa5501102a002f06120f002efb37029f8c54ed1e1d98eb6601de0d0000b00400005e01e7ff2823603be2044c04030e55004f03001b00136c"},
  {"alerte_perte_au2", "aa5501112b00070e030503000001ab5b"},
  {"commande_mode", "aa550120ffff010471b4"},
  {"commande_manuelle", "aa5501210c000818fcf4010000e8032510"},
  {"atterrissage", "aa5501220500008b8a"},
  {"retour_maison", "aa5501230600006fa5"},
  {"arret_urgence", "aa550124070002a55a866a"},
  {"mission_ack", "aa5501454d00060c0003020000bce2"},
  {"mission_verification", "aa5501464e00050c00030200f414"},
  {"texte_utf8", "aa55010402002301004d697373696f6e2076616c6964c3a9652c207072c3aa746520c3a020766f6c65723fa5"},
  {"distances_tourelle", "aa5501122d000b036cee94117800ffff54015f91"},
  {"mission_debut", "aa55014007000c0c0004000401b400fa00011e26eb"},
  {"mission_limites", "aa5501410800230c000480d51e1df0bb660180d51e1d100a670118101f1d100a670118101f1df0bb660138fd"},
  {"zone_interdite", "aa55014209001c0c00000308e91e1d30db6601d8f01e1d30db6601f0ec1e1de8e66601a398"},
  {"mission_waypoint_0", "aa5501430a00130c00000068d91e1dc0c36601f4010000fa0001ec44"},
  {"mission_waypoint_1", "aa5501430b00130c00010068d91e1d40026701f4010000fa00025792"},
  {"mission_waypoint_2", "aa5501430c00130c00020038e11e1d40026701f4010000fa0001eb56"},
  {"mission_waypoint_3", "aa5501430d00130c00030038e11e1dc0c36601f4010000fa00025080"},
  {"mission_fin", "aa5501440e00040c0083522cca"},
};
static const unsigned NB_VECTEURS_TRAMES = 23;
static const char *FLUX_HEX = "0013aa01aa550101010006050340e201002a17aa5501102a002f06120f002ebb37029f8c54ed1e1d98eb6601de0d0000b00400005e01e7ff2823603be2044c04030e55004f03001b00136caaaa5501022c01032411002c73";
static const uint16_t CRC_MISSION_ATTENDU = 0x5283;
