"""Contrats avec les modules voisins : une règle = un endroit.

Toute modification ici doit être faite en même temps dans :
  * protocole/SPECIFICATION.md § 12, FichiersVol.h, verifier_fichiers_vol.py (drone, AU2) ;
  * planificateur/js/config.js (CONFIG.cultures) et serveur_local.py (CULTURES) ;
  * pipeline/modeles.json (registre des modèles) ;
  * la notice du pipeline.
"""
from __future__ import annotations

import re

VERSION_PIPELINE = "1.1.0"

# --- Cultures (liste identique au planificateur et au registre des modèles) ----
CULTURES = ("ble", "mais", "pommier")
NOMS_CULTURES = {"ble": "Blé", "mais": "Maïs", "pommier": "Pommier"}

# --- Fichiers du vol (drone, AU2) ---------------------------------------------
FICHIER_PHOTOS = "photos.csv"
FICHIER_BOITE_NOIRE = "boite_noire.csv"
DOSSIER_IMAGES = "images"

ENTETE_PHOTOS = "fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission"
ENTETE_BOITE_NOIRE = "horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail"

HORODATAGE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
ENTIER = re.compile(r"^\d+$")
CODE_HEX = re.compile(r"^0x[0-9A-F]{2}$")

SOURCES = {"AU2", "AU1", "TOURELLE", "SOL", "PC", "INCONNU"}
CATEGORIES = {"ALERTE", "ORDRE", "MODE", "MISSION", "LIAISON", "SYSTEME"}
GRAVITES = ("INFO", "AVERTISSEMENT", "CRITIQUE", "URGENCE")
GRAVITES_SIGNALEES = ("CRITIQUE", "URGENCE")  # affichées en tête du rapport
ACTIONS = {"AUCUNE", "MAINTIEN_POSITION", "RETOUR_MAISON", "ATTERRISSAGE", "COUPURE_MOTEURS", "POURSUITE"}

# Détail de l'événement MISSION_CHARGEE : « mission 12, 4 waypoints »
MOTIF_MISSION_CHARGEE = re.compile(r"mission\s+(\d+)\s*,\s*(\d+)\s+waypoints?")

# --- Mission archivée (planificateur) ------------------------------------------
VERSION_MISSION = 1
MOTIF_FICHIER_MISSION = r"^mission_{id}(_(\d+))?\.json$"

# --- Registre des modèles ------------------------------------------------------
VERSION_REGISTRE = 1
TYPES_MODELE = ("classification", "detection", "deux_etages", "factice", "a_definir")

# --- Modules (pour nommer le fautif dans les erreurs) --------------------------
MODULE_DRONE = "drone (AU2)"
MODULE_CAMERA = "caméra ou transfert Wi-Fi"
MODULE_PLANIFICATEUR = "planificateur"
MODULE_REGISTRE = "registre des modèles / entraînement"
MODULE_PIPELINE = "pipeline"

# --- Réglages par défaut ---------------------------------------------------------
NB_TOP_MALADES = 10
NB_INCERTAINES = 10
TOLERANCE_HORLOGE_S = 600  # écart toléré entre l'horloge du PC et l'heure GPS (choix de la mission)
COTE_GRILLE_DEFAUT_M = 10.0  # v1, si la mission ne donne pas les paramètres caméra
COTE_GRILLE_V2_M = 2.0  # v2 : projection des détections
MODES_LOCALISATION = ("auto", "v1", "v2")
ECART_FORMAT_IMAGE = 0.03  # écart toléré entre le format de l'image et celui du capteur


class ErreurPipeline(Exception):
    """Erreur déclarée : entrées non conformes ou configuration incomplète.

    ``messages`` : liste de textes « fichier, ligne N : … [module fautif : …] ».
    """

    def __init__(self, etape: str, messages: list[str]):
        self.etape = etape
        self.messages = list(messages)
        super().__init__(f"{etape} : {len(self.messages)} erreur(s)")

    def format(self) -> str:
        lignes = [f"[ECHEC] {self.etape} : {len(self.messages)} erreur(s)"]
        lignes += [f"    - {m}" for m in self.messages]
        return "\n".join(lignes)


def erreur(fichier: str, texte: str, module: str, ligne: int | None = None) -> str:
    """Message d'erreur normalisé (règle de cohérence du projet)."""
    ou = f"{fichier}, ligne {ligne}" if ligne is not None else fichier
    return f"{ou} : {texte} [module fautif : {module}]"
