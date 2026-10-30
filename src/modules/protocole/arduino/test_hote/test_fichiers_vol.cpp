// Test sur PC de FichiersVol.h : lignes de photos.csv et de boite_noire.csv
// exactement conformes au contrat (SPECIFICATION.md § 12).
//   make -C protocole/arduino/test_hote test
#include <cstdio>
#include <cstring>

#include "../ProtocoleDrone/FichiersVol.h"

static int echecs = 0;

static void attendre(const char *obtenu, const char *attendu, int ligne) {
  if (std::strcmp(obtenu, attendu) != 0) {
    std::printf("ÉCHEC ligne %d\n  obtenu  : \"%s\"\n  attendu : \"%s\"\n", ligne, obtenu, attendu);
    echecs++;
  }
}
#define ATTENDRE(obtenu, attendu) attendre(obtenu, attendu, __LINE__)
#define VERIFIER(cond)                                                    \
  do {                                                                    \
    if (!(cond)) { std::printf("ÉCHEC %d : %s\n", __LINE__, #cond); echecs++; } \
  } while (0)

int main() {
  char l[TAILLE_LIGNE_MAX];
  const HeureUtc h = {2026, 11, 2, 14, 5, 12, true};
  const HeureUtc sansHeure = {0, 0, 0, 0, 0, 0, false};

  // 1. En-têtes : le contrat avec le pipeline d'analyse
  ATTENDRE(ENTETE_PHOTOS_CSV, "fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission");
  ATTENDRE(ENTETE_BOITE_NOIRE_CSV,
           "horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail");

  // 2. Nom imposé à la caméra
  VERIFIER(nomFichierPhoto(l, sizeof l, 1) == 12);
  ATTENDRE(l, "IMG_0001.JPG");
  nomFichierPhoto(l, sizeof l, 237);
  ATTENDRE(l, "IMG_0237.JPG");

  // 3. photos.csv : l'exemple de la notice du pipeline, à l'octet près
  LignePhoto p = {"IMG_0001.JPG", h, 483010580, 16030366, 1000, 8750, 0, 1};
  VERIFIER(formaterLignePhoto(l, sizeof l, p) > 0);
  ATTENDRE(l, "IMG_0001.JPG;2026-11-02T14:05:12Z;48.3010580;1.6030366;10.00;87.5;0;1");

  // Coordonnées négatives, zéros de tête, cap arrondi et 359,96° ramené à 0,0
  LignePhoto q = {"IMG_0042.JPG", {2027, 1, 9, 3, 4, 5, true}, -5000000, -1234567890, -35, 35996, 12, 65535};
  formaterLignePhoto(l, sizeof l, q);
  ATTENDRE(l, "IMG_0042.JPG;2027-01-09T03:04:05Z;-0.5000000;-123.4567890;-0.35;0.0;12;65535");
  q.cap_cdeg = 4;  // 0,04° -> 0,0
  formaterLignePhoto(l, sizeof l, q);
  VERIFIER(std::strstr(l, ";0.0;12;") != nullptr);
  q.cap_cdeg = 18005;  // 180,05° -> 180,1 (arrondi)
  formaterLignePhoto(l, sizeof l, q);
  VERIFIER(std::strstr(l, ";180.1;12;") != nullptr);

  // Pas d'heure GPS, ou pas de nom : ligne refusée (AU2 écrit une alerte à la place)
  LignePhoto r = p;
  r.heure = sansHeure;
  VERIFIER(formaterLignePhoto(l, sizeof l, r) == 0 && l[0] == '\0');
  r = p;
  r.fichier = "";
  VERIFIER(formaterLignePhoto(l, sizeof l, r) == 0);
  // Tampon trop petit : refus plutôt qu'une ligne tronquée
  char petit[20];
  VERIFIER(formaterLignePhoto(petit, sizeof petit, p) == 0 && petit[0] == '\0');

  // 4. boite_noire.csv
  MsgAlerteAvarie a = {AVARIE_PERTE_LIAISON_AU2, GRAVITE_URGENCE, EMETTEUR_AU1, ACTION_ATTERRISSAGE, 0, 1};
  EvenementVol e = evenementAlerte(a, h, 754321);
  formaterLigneBoiteNoire(l, sizeof l, e);
  ATTENDRE(l, "2026-11-02T14:05:12Z;754321;AU1;ALERTE;0x0E;PERTE_LIAISON_AU2;URGENCE;ATTERRISSAGE;0;1;");

  // Ordre reçu de la LoRa, avant que le GPS ait l'heure (horodatage vide), détail nettoyé
  EvenementVol o = {sansHeure, 1500, EMETTEUR_BOITIER_SOL, CATEGORIE_ORDRE, TYPE_ARRET_URGENCE, nullptr,
                    GRAVITE_URGENCE, ACTION_COUPURE_MOTEURS, 0, -1, "1re demande; attente\nconfirmation"};
  formaterLigneBoiteNoire(l, sizeof l, o);
  ATTENDRE(l, ";1500;SOL;ORDRE;0x24;ARRET_URGENCE;URGENCE;COUPURE_MOTEURS;0;;1re demande, attente confirmation");

  // Mission refusée par AU2 (statut 6), valeur négative, nom explicite
  EvenementVol m = {h, 42, EMETTEUR_AU2, CATEGORIE_MISSION, MISSION_ETAT_INCOMPATIBLE, "MISSION_REFUSEE",
                    GRAVITE_AVERTISSEMENT, ACTION_AUCUNE, -12, -1, "drone arme"};
  formaterLigneBoiteNoire(l, sizeof l, m);
  ATTENDRE(l, "2026-11-02T14:05:12Z;42;AU2;MISSION;0x06;MISSION_REFUSEE;AVERTISSEMENT;AUCUNE;-12;;drone arme");

  // Nombre de colonnes constant (11) quel que soit l'événement
  int pointsVirgules = 0;
  for (const char *c = l; *c; c++) pointsVirgules += (*c == ';');
  VERIFIER(pointsVirgules == 10);

  if (echecs == 0) {
    std::printf("OK : photos.csv et boite_noire.csv conformes au contrat.\n");
    return 0;
  }
  std::printf("%d échec(s)\n", echecs);
  return 1;
}
