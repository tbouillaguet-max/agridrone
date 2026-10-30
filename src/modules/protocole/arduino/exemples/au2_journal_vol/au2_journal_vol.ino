// =============================================================================
// AU2 — journal de vol sur la carte SD : photos.csv et boite_noire.csv
//
// Exemple autonome (pas le programme de vol) qui montre comment AU2 écrit ses
// deux fichiers sur SA carte SD, au format exact de SPECIFICATION.md § 12
// (contrat avec le pipeline d'analyse des images : ne pas changer les colonnes).
//
//   /vols/mission_<id>_<n>/photos.csv       une ligne par photo déclenchée
//   /vols/mission_<id>_<n>/boite_noire.csv  une ligne par alerte, erreur, ordre…
//
// Règles appliquées (§ 12.1) :
//  - un dossier par vol, créé au décollage (n = 1, 2… si la même mission vole
//    plusieurs fois) ;
//  - chaque ligne est écrite PUIS synchronisée (sync) : une coupure de
//    courant ne perd au plus que la ligne en cours (boîte noire) ;
//  - si la carte SD ne répond plus : alerte DEFAUT_SD envoyée par LoRa (pas
//    d'écriture possible), action retour maison.
//
// Ici, le GPS, la caméra et la LoRa sont simulés : une « photo » toutes les
// 2 s et quelques événements. Moniteur série : 115200 bauds.
//
// Matériel : lecteur SD SPI sur AU2 (CS broche 53, SCK 52, MOSI 51, MISO 50).
// Bibliothèques : ProtocoleDrone (ce dépôt) et SdFat (Bill Greiman, gestionnaire
// de bibliothèques) — SdFat gère les noms longs, contrairement à SD.h (8.3).
// =============================================================================
#include <SdFat.h>
#include <ProtocoleDrone.h>
#include <FichiersVol.h>

const uint8_t BROCHE_CS_SD = 53;

SdFat sd;
FsFile fichierPhotos, fichierBoiteNoire;
bool sdOk = false;
char dossierVol[40];
char ligne[TAILLE_LIGNE_MAX];

// --- GPS simulé (le vrai AU2 lit l'heure et la position du GPS) ----------------
HeureUtc heureGps() {
  uint32_t s = millis() / 1000;
  HeureUtc h = {2026, 11, 2, 14, (uint8_t)((5 + s / 60) % 60), (uint8_t)(s % 60), true};
  return h;
}

// --- écriture d'une ligne puis synchronisation -----------------------------------
bool ecrireLigne(FsFile &f, const char *texte, size_t n) {
  if (!sdOk || n == 0) return false;
  bool ok = f.write(texte, n) == n && f.write('\n') == 1 && f.sync();
  if (!ok) {
    sdOk = false;
    // Plus de carte SD : la LoRa est le seul moyen de prévenir le sol.
    MsgAlerteAvarie a = {AVARIE_DEFAUT_SD, GRAVITE_CRITIQUE, EMETTEUR_AU2, ACTION_RETOUR_MAISON, 0, 1};
    (void)a;  // envoyerLora(TYPE_ALERTE_AVARIE, a);
    Serial.println(F("!! DEFAUT_SD : écriture impossible"));
  }
  return ok;
}

void journaliser(const EvenementVol &e) {
  size_t n = formaterLigneBoiteNoire(ligne, sizeof ligne, e);
  Serial.print(F("boite_noire : "));
  Serial.println(ligne);
  ecrireLigne(fichierBoiteNoire, ligne, n);
}

void journaliserSysteme(uint8_t gravite, const char *nom, const char *detail) {
  EvenementVol e = {heureGps(), millis(), EMETTEUR_AU2, CATEGORIE_SYSTEME, 0, nom, gravite, ACTION_AUCUNE, 0, -1, detail};
  journaliser(e);
}

// --- ouverture du dossier du vol ----------------------------------------------------
bool ouvrirFichier(FsFile &f, const char *nom, const char *entete) {
  char chemin[64];
  snprintf(chemin, sizeof chemin, "%s/%s", dossierVol, nom);
  bool existe = sd.exists(chemin);
  if (!f.open(chemin, O_WRONLY | O_CREAT | O_APPEND)) return false;
  if (!existe) return ecrireLigne(f, entete, strlen(entete));
  return true;
}

bool debutVol(uint16_t idMission) {
  if (!sd.exists("/vols") && !sd.mkdir("/vols")) return false;
  for (uint8_t n = 1; n < 100; n++) {
    snprintf(dossierVol, sizeof dossierVol, "/vols/mission_%05u_%02u", idMission, n);
    if (!sd.exists(dossierVol)) break;
  }
  if (!sd.mkdir(dossierVol)) return false;
  return ouvrirFichier(fichierPhotos, "photos.csv", ENTETE_PHOTOS_CSV) &&
         ouvrirFichier(fichierBoiteNoire, "boite_noire.csv", ENTETE_BOITE_NOIRE_CSV);
}

// --- une photo : nom imposé à la caméra, puis ligne de photos.csv -----------------
uint16_t numeroPhoto = 0;

void photo(uint16_t idMission, uint16_t waypoint) {
  char nom[16];
  nomFichierPhoto(nom, sizeof nom, ++numeroPhoto);
  // declencherCamera(nom);   // TO DO : dépend du modèle de caméra (programmable)
  LignePhoto p = {nom, heureGps(), 483010580L + numeroPhoto * 20L, 16030366L, 1000, 8750, waypoint, idMission};
  size_t n = formaterLignePhoto(ligne, sizeof ligne, p);
  if (n == 0) {
    // Pas d'heure GPS (ou nom vide) : on n'écrit pas une ligne fausse, on le signale.
    EvenementVol e = {heureGps(), millis(), EMETTEUR_AU2, CATEGORIE_ALERTE, AVARIE_GPS_PERDU, nullptr,
                      GRAVITE_AVERTISSEMENT, ACTION_POURSUITE, (int16_t)numeroPhoto, 1, "photo sans heure GPS"};
    journaliser(e);
    return;
  }
  Serial.print(F("photos.csv : "));
  Serial.println(ligne);
  ecrireLigne(fichierPhotos, ligne, n);
}

void setup() {
  Serial.begin(115200);
  sdOk = sd.begin(SdSpiConfig(BROCHE_CS_SD, DEDICATED_SPI, SD_SCK_MHZ(16)));
  if (!sdOk) { Serial.println(F("carte SD absente")); return; }
  const uint16_t idMission = 12;  // le vrai AU2 prend l'id de la mission chargée (MISSION_DEBUT)
  if (!debutVol(idMission)) { sdOk = false; Serial.println(F("dossier du vol impossible")); return; }
  Serial.print(F("dossier du vol : "));
  Serial.println(dossierVol);
  journaliserSysteme(GRAVITE_INFO, "DEBUT_VOL", "mission 12");

  // Exemples d'événements
  MsgAlerteAvarie a = {AVARIE_BATTERIE_FAIBLE, GRAVITE_AVERTISSEMENT, EMETTEUR_AU1, ACTION_RETOUR_MAISON, 142, 1};
  journaliser(evenementAlerte(a, heureGps(), millis()));
  EvenementVol o = {heureGps(), millis(), EMETTEUR_BOITIER_SOL, CATEGORIE_ORDRE, TYPE_RETOUR_MAISON, nullptr,
                    GRAVITE_AVERTISSEMENT, ACTION_RETOUR_MAISON, 0, -1, "ordre LoRa"};
  journaliser(o);
}

void loop() {
  static uint32_t prochaine = 0;
  if (sdOk && (int32_t)(millis() - prochaine) >= 0 && numeroPhoto < 20) {
    photo(12, numeroPhoto / 5);
    prochaine = millis() + 2000;
  }
}
