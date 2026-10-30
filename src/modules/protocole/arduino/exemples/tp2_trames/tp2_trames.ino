// =============================================================================
// TP — étape 2 : trames du protocole commun sur la liaison AU2 <-> AU1
//
// Ce croquis tourne sur AU2 (navigation). Montage : Serial1 d'AU2 (broches
// 18 TX1 et 19 RX1) croisé avec Serial1 d'AU1 (TX1 -> RX1, RX1 <- TX1, masses
// communes) ; câble USB d'AU2 vers le PC pour le moniteur série (115200
// bauds), qui affiche toutes les trames reçues. Pour un essai sans AU1, un
// adaptateur USB-série branché sur un second PC peut jouer AU1.
//
// Comportement (sous-ensemble d'AU2, SPECIFICATION.md § 4 et § 10) :
//  - HEARTBEAT toutes les 500 ms (émetteur 0x00 = AU2) ;
//  - surveillance du HEARTBEAT d'AU1 : silence > 2 s ⇒ « PERTE AU1 » sur le
//    moniteur, LED allumée, et ALERTE_AVARIE 0x0D (PERTE_LIAISON_AU1) ;
//    sur le vrai AU2, chaque alerte est aussi écrite dans la boîte noire ;
//  - TEXTE reçu ⇒ réponse TEXTE « AU2 : reçu <texte> » ;
//  - type inconnu ⇒ NACK (code 2, TYPE_INCONNU) ;
//  - statistiques de la liaison toutes les 10 s.
//
// Bibliothèque : protocole/arduino/ProtocoleDrone (copier le dossier dans
// Documents/Arduino/libraries, ou arduino-cli --library <chemin>).
// =============================================================================
#include <ProtocoleDrone.h>

#define LIAISON Serial1               // vers AU1
#define MONITEUR Serial               // vers le PC
const unsigned long DEBIT = 115200;

DecodeurTrame decodeur;               // un décodeur par liaison
uint16_t sequence = 0;                // un compteur de séquence par liaison
uint8_t tampon[TAILLE_TRAME_MAX];     // tampon d'émission

uint32_t prochainHeartbeat = 0;
uint32_t dernierHeartbeatAu1 = 0;
bool au1Vu = false;
bool au1Perdu = false;
uint32_t prochainesStats = 10000;

// --- émission -----------------------------------------------------------------
template <typename T>
void envoyer(uint8_t type, const T &message) {
  LIAISON.write(tampon, encoderMessage(tampon, type, sequence++, message));
}

void envoyerTexte(const char *texte) {
  MsgTexteEntete entete = { 1 /* info */, EMETTEUR_AU2 };
  size_t n = strlen(texte);
  if (n > 200) n = 200;
  LIAISON.write(tampon, encoderTrame2(tampon, TYPE_TEXTE, sequence++, &entete, sizeof entete, texte, n));
}

// --- réception ----------------------------------------------------------------
void traiterTrame(const TrameRecue &t) {
  MONITEUR.print(F("<- type 0x"));
  MONITEUR.print(t.type, HEX);
  MONITEUR.print(F(" seq "));
  MONITEUR.print(t.sequence);
  MONITEUR.print(F(" ("));
  MONITEUR.print(t.longueur);
  MONITEUR.print(F(" o)"));

  switch (t.type) {
    case TYPE_HEARTBEAT: {
      MsgHeartbeat hb;
      if (decodeur.lire(hb) && hb.emetteur == EMETTEUR_AU1) {
        dernierHeartbeatAu1 = millis();
        au1Vu = true;
        MONITEUR.print(F(" HEARTBEAT d'AU1, état 0x"));
        MONITEUR.print(hb.etat, HEX);
      }
      break;
    }
    case TYPE_TEXTE: {
      char texte[201];
      uint8_t n = t.longueur > 2 ? t.longueur - 2 : 0;
      memcpy(texte, t.donnees + 2, n);
      texte[n] = '\0';
      MONITEUR.print(F(" TEXTE : "));
      MONITEUR.print(texte);
      char reponse[220];
      snprintf(reponse, sizeof reponse, "AU2 : reçu %s", texte);
      envoyerTexte(reponse);
      break;
    }
    case TYPE_ALERTE_AVARIE: {
      MsgAlerteAvarie a;
      if (decodeur.lire(a)) {
        MONITEUR.print(F(" ALERTE 0x"));
        MONITEUR.print(a.code, HEX);
        MONITEUR.print(a.actif ? F(" active") : F(" terminée"));
      }
      break;
    }
    default: {
      MsgNack nack = { t.type, t.sequence, NACK_TYPE_INCONNU };
      envoyer(TYPE_NACK, nack);
      MONITEUR.print(F(" type non géré : NACK envoyé"));
    }
  }
  MONITEUR.println();
}

// --- programme ----------------------------------------------------------------
void setup() {
  LIAISON.begin(DEBIT);
  MONITEUR.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  MONITEUR.println(F("tp2_trames : AU2 prêt (AU1 sur Serial1, 115200 8N1)"));
}

void loop() {
  uint32_t maintenant = millis();

  // 1. Réception : on pousse chaque octet dans le décodeur
  while (LIAISON.available()) {
    if (decodeur.pousser(LIAISON.read(), maintenant)) traiterTrame(decodeur.trame());
  }

  // 2. Heartbeat d'AU2
  if ((int32_t)(maintenant - prochainHeartbeat) >= 0) {
    uint8_t etat = DRAPEAU_DEPART_DEFINI;
    if (au1Vu && !au1Perdu) etat |= DRAPEAU_LIAISON_AU_OK;
    MsgHeartbeat hb = { EMETTEUR_AU2, etat, maintenant };
    envoyer(TYPE_HEARTBEAT, hb);
    prochainHeartbeat = maintenant + PERIODE_HEARTBEAT_MS;
  }

  // 3. Surveillance du heartbeat d'AU1
  bool silence = au1Vu && (maintenant - dernierHeartbeatAu1 > DELAI_PERTE_LIAISON_MS);
  if (silence && !au1Perdu) {
    au1Perdu = true;
    digitalWrite(LED_BUILTIN, HIGH);
    MONITEUR.println(F("!! PERTE AU1 (plus de heartbeat depuis 2 s)"));
    MsgAlerteAvarie a = { AVARIE_PERTE_LIAISON_AU1, GRAVITE_CRITIQUE, EMETTEUR_AU2, ACTION_AUCUNE, 0, 1 };
    envoyer(TYPE_ALERTE_AVARIE, a);
  } else if (!silence && au1Perdu) {
    au1Perdu = false;
    digitalWrite(LED_BUILTIN, LOW);
    MONITEUR.println(F("AU1 de retour"));
    MsgAlerteAvarie a = { AVARIE_PERTE_LIAISON_AU1, GRAVITE_INFO, EMETTEUR_AU2, ACTION_AUCUNE, 0, 0 };
    envoyer(TYPE_ALERTE_AVARIE, a);
  }

  // 4. Statistiques
  if ((int32_t)(maintenant - prochainesStats) >= 0) {
    MONITEUR.print(F("stats : trames valides "));
    MONITEUR.print(decodeur.tramesValides);
    MONITEUR.print(F(", erreurs CRC "));
    MONITEUR.print(decodeur.erreursCrc);
    MONITEUR.print(F(", incomplètes "));
    MONITEUR.println(decodeur.tramesIncompletes);
    prochainesStats = maintenant + 10000;
  }
}
