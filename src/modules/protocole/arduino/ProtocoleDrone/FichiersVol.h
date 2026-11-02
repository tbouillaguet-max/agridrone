// =============================================================================
// FichiersVol.h — lignes des fichiers écrits par AU2 sur sa carte SD
//
// Référence : protocole/SPECIFICATION.md § 12 (contrat avec le pipeline
// d'analyse des images : NE PAS modifier les colonnes sans prévenir).
//
//   photos.csv       une ligne par photo déclenchée
//   boite_noire.csv  une ligne par alerte, erreur, ordre, changement de mode
//
// Ce fichier ne fait QUE mettre en forme des lignes de texte dans un tampon
// (pas d'accès à la carte SD) : il compile pour AVR comme pour un PC, et il
// est testé sur PC (protocole/arduino/test_hote/test_fichiers_vol.cpp).
// L'écriture sur la SD est faite par le croquis (exemple : exemples/au2_journal_vol).
//
// Pas de printf("%f") (absent sur AVR) : tous les nombres sont des entiers
// mis en forme ici (degrés × 10⁷, centimètres, centidegrés).
// =============================================================================
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#include "ProtocoleDrone.h"

// En-têtes exacts (première ligne de chaque fichier)
static const char ENTETE_PHOTOS_CSV[] =
    "fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission";
static const char ENTETE_BOITE_NOIRE_CSV[] =
    "horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail";

static const size_t TAILLE_LIGNE_MAX = 192;  // tampon conseillé pour une ligne (avec '\n' et '\0')

// Heure UTC donnée par le GPS. valide = false tant que le GPS n'a pas l'heure.
struct HeureUtc {
  uint16_t annee;
  uint8_t mois, jour, heure, minute, seconde;
  bool valide;
};

// Catégories de la boîte noire
enum CategorieEvenement : uint8_t {
  CATEGORIE_ALERTE = 0,   // ALERTE_AVARIE émise ou reçue (AU1, AU2, tourelle)
  CATEGORIE_ORDRE = 1,    // ordre reçu : ATTERRISSAGE, RETOUR_MAISON, ARRET_URGENCE, COMMANDE_MODE
  CATEGORIE_MODE = 2,     // changement de mode de vol, armement, désarmement
  CATEGORIE_MISSION = 3,  // mission chargée, refusée (statut), début, fin
  CATEGORIE_LIAISON = 4,  // trames rejetées, NACK, perte et retour d'une liaison
  CATEGORIE_SYSTEME = 5,  // démarrage, carte SD, caméra
};

// ----------------------------------------------------------------------------
// Petit écrivain borné : n'écrit jamais au-delà de la taille du tampon.
// ----------------------------------------------------------------------------
class LigneTexte {
 public:
  LigneTexte(char *tampon, size_t taille) : t_(tampon), taille_(taille), n_(0), deborde_(false) {
    if (taille_) t_[0] = '\0';
  }

  LigneTexte &car(char c) {
    if (n_ + 1 < taille_) { t_[n_++] = c; t_[n_] = '\0'; } else deborde_ = true;
    return *this;
  }

  LigneTexte &texte(const char *s) {
    while (s && *s) car(*s++);
    return *this;
  }

  // Texte libre : « ; », retours à la ligne et guillemets remplacés (le CSV reste lisible).
  LigneTexte &texteLibre(const char *s) {
    while (s && *s) {
      char c = *s++;
      car(c == ';' ? ',' : (c == '\n' || c == '\r') ? ' ' : c == '"' ? '\'' : c);
    }
    return *this;
  }

  LigneTexte &entier(int32_t v) {
    if (v < 0) { car('-'); return naturel((uint32_t)(-(v + 1)) + 1u); }
    return naturel((uint32_t)v);
  }

  LigneTexte &naturel(uint32_t v, uint8_t chiffresMin = 1) {
    char c[10];
    uint8_t n = 0;
    do { c[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n < chiffresMin && n < sizeof c) c[n++] = '0';
    while (n) car(c[--n]);
    return *this;
  }

  // Nombre décimal à partir d'un entier mis à l'échelle : decimal(1234, 2) -> "12.34"
  LigneTexte &decimal(int32_t valeur, uint8_t decimales) {
    uint32_t div = 1;
    for (uint8_t i = 0; i < decimales; i++) div *= 10;
    bool negatif = valeur < 0;
    uint32_t a = negatif ? (uint32_t)(-(valeur + 1)) + 1u : (uint32_t)valeur;
    if (negatif) car('-');
    naturel(a / div);
    if (decimales) { car('.'); naturel(a % div, decimales); }
    return *this;
  }

  LigneTexte &hex2(uint8_t v) {
    static const char H[] = "0123456789ABCDEF";
    return texte("0x").car(H[v >> 4]).car(H[v & 15]);
  }

  size_t longueur() const { return n_; }
  bool deborde() const { return deborde_; }

 private:
  char *t_;
  size_t taille_, n_;
  bool deborde_;
};

// Horodatage ISO 8601 UTC : "2026-11-02T14:05:12Z" ; rien si l'heure n'est pas valide.
static inline LigneTexte &ajouterHorodatage(LigneTexte &l, const HeureUtc &h) {
  if (!h.valide) return l;
  l.naturel(h.annee, 4).car('-').naturel(h.mois, 2).car('-').naturel(h.jour, 2).car('T');
  return l.naturel(h.heure, 2).car(':').naturel(h.minute, 2).car(':').naturel(h.seconde, 2).car('Z');
}

// ----------------------------------------------------------------------------
// photos.csv (§ 12.2)
// ----------------------------------------------------------------------------
struct LignePhoto {
  const char *fichier;         // nom imposé par AU2 à la caméra, ex. "IMG_0001.JPG"
  HeureUtc heure;              // instant du déclenchement (heure GPS)
  int32_t latitude_e7;
  int32_t longitude_e7;
  int32_t altitude_relative_cm;
  uint16_t cap_cdeg;           // 0..35999, nord = 0 (magnétomètre d'AU2)
  uint16_t index_waypoint;     // dernier waypoint atteint
  uint16_t id_mission;
};

// Écrit la ligne SANS retour à la ligne. Renvoie sa longueur, ou 0 si elle est
// refusée (heure GPS absente, nom vide, tampon trop petit) : dans ce cas AU2
// écrit une alerte dans la boîte noire au lieu d'une ligne fausse.
static inline size_t formaterLignePhoto(char *tampon, size_t taille, const LignePhoto &p) {
  if (!p.heure.valide || !p.fichier || !p.fichier[0]) { if (taille) tampon[0] = '\0'; return 0; }
  LigneTexte l(tampon, taille);
  l.texteLibre(p.fichier).car(';');
  ajouterHorodatage(l, p.heure).car(';');
  l.decimal(p.latitude_e7, 7).car(';').decimal(p.longitude_e7, 7).car(';');
  l.decimal(p.altitude_relative_cm, 2).car(';');
  // centidegrés -> dixièmes de degré arrondis, 360.0 ramené à 0.0
  uint32_t dixiemes = ((uint32_t)p.cap_cdeg % 36000u + 5u) / 10u;
  if (dixiemes >= 3600u) dixiemes = 0;
  l.decimal((int32_t)dixiemes, 1).car(';');
  l.naturel(p.index_waypoint).car(';').naturel(p.id_mission);
  if (l.deborde()) { tampon[0] = '\0'; return 0; }
  return l.longueur();
}

// Nom de fichier imposé à la caméra : "IMG_0001.JPG" (numéro de 1 à 9999 dans la mission).
static inline size_t nomFichierPhoto(char *tampon, size_t taille, uint16_t numero) {
  LigneTexte l(tampon, taille);
  l.texte("IMG_").naturel(numero % 10000u, 4).texte(".JPG");
  return l.deborde() ? 0 : l.longueur();
}

// ----------------------------------------------------------------------------
// boite_noire.csv (§ 12.3)
// ----------------------------------------------------------------------------
static inline const char *nomSource(uint8_t s) {
  switch (s) {
    case EMETTEUR_AU2: return "AU2";
    case EMETTEUR_UNO: return "TOURELLE";
    case EMETTEUR_BOITIER_SOL: return "SOL";
    case EMETTEUR_PLANIFICATEUR: return "PC";
    case EMETTEUR_AU1: return "AU1";
    default: return "INCONNU";
  }
}

static inline const char *nomCategorie(uint8_t c) {
  static const char *const N[] = {"ALERTE", "ORDRE", "MODE", "MISSION", "LIAISON", "SYSTEME"};
  return c < 6 ? N[c] : "INCONNU";
}

static inline const char *nomGravite(uint8_t g) {
  static const char *const N[] = {"INFO", "AVERTISSEMENT", "CRITIQUE", "URGENCE"};
  return g < 4 ? N[g] : "INCONNU";
}

static inline const char *nomAction(uint8_t a) {
  static const char *const N[] = {"AUCUNE", "MAINTIEN_POSITION", "RETOUR_MAISON", "ATTERRISSAGE",
                                  "COUPURE_MOTEURS", "POURSUITE"};
  return a < 6 ? N[a] : "INCONNU";
}

static inline const char *nomAvarie(uint8_t code) {
  switch (code) {
    case AVARIE_PERTE_LIAISON_LORA: return "PERTE_LIAISON_LORA";
    case AVARIE_PERTE_LIAISON_TOURELLE: return "PERTE_LIAISON_TOURELLE";
    case AVARIE_BATTERIE_FAIBLE: return "BATTERIE_FAIBLE";
    case AVARIE_BATTERIE_CRITIQUE: return "BATTERIE_CRITIQUE";
    case AVARIE_GPS_PERDU: return "GPS_PERDU";
    case AVARIE_GEOFENCE: return "GEOFENCE";
    case AVARIE_OBSTACLE: return "OBSTACLE";
    case AVARIE_DEFAUT_IMU: return "DEFAUT_IMU";
    case AVARIE_DEFAUT_BARO: return "DEFAUT_BARO";
    case AVARIE_DEFAUT_BOUSSOLE: return "DEFAUT_BOUSSOLE";
    case AVARIE_DEFAUT_MOTEUR: return "DEFAUT_MOTEUR";
    case AVARIE_PERTE_LIAISON_AU1: return "PERTE_LIAISON_AU1";
    case AVARIE_PERTE_LIAISON_AU2: return "PERTE_LIAISON_AU2";
    case AVARIE_DEFAUT_SD: return "DEFAUT_SD";
    case AVARIE_DEFAUT_CAMERA: return "DEFAUT_CAMERA";
    case AVARIE_ARRET_URGENCE: return "ARRET_URGENCE";
    case AVARIE_ERREUR_LIAISON: return "ERREUR_LIAISON";
    case AVARIE_REDEMARRAGE: return "REDEMARRAGE";
    default: return "AVARIE_INCONNUE";
  }
}

// Nom d'un type de message (catégorie ORDRE ou LIAISON)
static inline const char *nomTypeMessage(uint8_t type) {
  switch (type) {
    case TYPE_COMMANDE_MODE: return "COMMANDE_MODE";
    case TYPE_COMMANDE_MANUELLE: return "COMMANDE_MANUELLE";
    case TYPE_ATTERRISSAGE: return "ATTERRISSAGE";
    case TYPE_RETOUR_MAISON: return "RETOUR_MAISON";
    case TYPE_ARRET_URGENCE: return "ARRET_URGENCE";
    case TYPE_MISSION_DEBUT: return "MISSION_DEBUT";
    case TYPE_MISSION_FIN: return "MISSION_FIN";
    case TYPE_NACK: return "NACK";
    default: return "MESSAGE";
  }
}

struct EvenementVol {
  HeureUtc heure;      // laisser valide = false avant que le GPS ait l'heure
  uint32_t temps_ms;   // millis() d'AU2 : toujours renseigné
  uint8_t source;      // § 3
  uint8_t categorie;   // CategorieEvenement
  uint8_t code;        // ALERTE : code d'avarie ; ORDRE/LIAISON : type de message ; MODE : mode ; MISSION : statut
  const char *nom;     // nul => nom déduit de la catégorie et du code
  uint8_t gravite;     // Gravite
  uint8_t action;      // ActionAvarie
  int16_t valeur;
  int8_t actif;        // 1, 0, ou -1 = sans objet (colonne vide)
  const char *detail;  // texte libre court, peut être nul
};

static inline const char *nomEvenement(const EvenementVol &e) {
  if (e.nom) return e.nom;
  switch (e.categorie) {
    case CATEGORIE_ALERTE: return nomAvarie(e.code);
    case CATEGORIE_ORDRE:
    case CATEGORIE_LIAISON: return nomTypeMessage(e.code);
    default: return nomCategorie(e.categorie);
  }
}

// Écrit la ligne SANS retour à la ligne ; renvoie sa longueur (0 si le tampon est trop petit).
static inline size_t formaterLigneBoiteNoire(char *tampon, size_t taille, const EvenementVol &e) {
  LigneTexte l(tampon, taille);
  ajouterHorodatage(l, e.heure).car(';');
  l.naturel(e.temps_ms).car(';');
  l.texte(nomSource(e.source)).car(';');
  l.texte(nomCategorie(e.categorie)).car(';');
  l.hex2(e.code).car(';');
  l.texteLibre(nomEvenement(e)).car(';');
  l.texte(nomGravite(e.gravite)).car(';');
  l.texte(nomAction(e.action)).car(';');
  l.entier(e.valeur).car(';');
  if (e.actif >= 0) l.naturel((uint32_t)e.actif);
  l.car(';');
  l.texteLibre(e.detail);
  if (l.deborde()) { if (taille) tampon[0] = '\0'; return 0; }
  return l.longueur();
}

// Ligne de boîte noire pour une ALERTE_AVARIE reçue ou émise.
static inline EvenementVol evenementAlerte(const MsgAlerteAvarie &a, const HeureUtc &h, uint32_t tempsMs) {
  EvenementVol e = {h, tempsMs, a.source, CATEGORIE_ALERTE, a.code, nullptr, a.gravite, a.action, a.valeur,
                    (int8_t)(a.actif ? 1 : 0), nullptr};
  return e;
}
