#!/usr/bin/env python3
"""Vérifie les fichiers d'un vol écrits par AU2 (SPECIFICATION.md § 12).

Contrôle, ligne par ligne, que photos.csv et boite_noire.csv respectent le
contrat avec le pipeline d'analyse des images, et (si l'on donne le dossier
des images) que chaque photo a sa ligne et inversement. Chaque erreur nomme
le fichier, la ligne et le module fautif (règle de cohérence du projet).

Usage :
    python verifier_fichiers_vol.py DOSSIER_DU_VOL
        DOSSIER_DU_VOL contient photos.csv, boite_noire.csv et (facultatif) images/
    python verifier_fichiers_vol.py DOSSIER_DU_VOL --mission chemin/mission_12.json

Code de sortie : 0 si tout est conforme, 1 sinon. Bibliothèque standard seulement.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENTETE_PHOTOS = "fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission"
ENTETE_BOITE_NOIRE = "horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail"

HORODATAGE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DECIMAL = re.compile(r"^-?\d+(\.\d+)?$")
ENTIER = re.compile(r"^\d+$")
SOURCES = {"AU2", "AU1", "TOURELLE", "SOL", "PC", "INCONNU"}
CATEGORIES = {"ALERTE", "ORDRE", "MODE", "MISSION", "LIAISON", "SYSTEME"}
GRAVITES = {"INFO", "AVERTISSEMENT", "CRITIQUE", "URGENCE"}
ACTIONS = {"AUCUNE", "MAINTIEN_POSITION", "RETOUR_MAISON", "ATTERRISSAGE", "COUPURE_MOTEURS", "POURSUITE"}
MODULE = "drone (AU2)"


def lire_lignes(chemin: Path, erreurs: list[str]) -> list[str] | None:
    try:
        octets = chemin.read_bytes()
    except FileNotFoundError:
        erreurs.append(f"{chemin.name} : fichier absent [module fautif : {MODULE}]")
        return None
    if octets.startswith(b"\xef\xbb\xbf"):
        erreurs.append(f"{chemin.name} : marque BOM interdite (UTF-8 sans BOM) [module fautif : {MODULE}]")
        octets = octets[3:]
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError as e:
        erreurs.append(f"{chemin.name} : pas en UTF-8 ({e}) [module fautif : {MODULE}]")
        return None
    return [l.rstrip("\r") for l in texte.split("\n") if l.strip()]


def verifier_photos(chemin: Path, erreurs: list[str], mission: dict | None) -> list[str]:
    """Renvoie la liste des noms de fichiers décrits."""
    lignes = lire_lignes(chemin, erreurs)
    if lignes is None:
        return []
    nom = chemin.name
    def err(n: int, texte: str) -> None:
        erreurs.append(f"{nom}, ligne {n} : {texte} [module fautif : {MODULE}]")
    if not lignes or lignes[0] != ENTETE_PHOTOS:
        err(1, f"en-tête attendu « {ENTETE_PHOTOS} », lu « {lignes[0] if lignes else ''} »")
        return []
    fichiers: list[str] = []
    ids: set[str] = set()
    nb_wp = len(mission.get("waypoints", [])) if mission else None
    for n, ligne in enumerate(lignes[1:], start=2):
        c = ligne.split(";")
        if len(c) != 8:
            err(n, f"{len(c)} colonnes au lieu de 8")
            continue
        fichier, heure, lat, lon, alt, cap, wp, idm = c
        if not fichier:
            err(n, "nom de fichier vide")
        elif fichier in fichiers:
            err(n, f"photo « {fichier} » déjà décrite")
        fichiers.append(fichier)
        if not HORODATAGE.match(heure):
            err(n, f"horodatage_utc « {heure} » : ISO 8601 UTC attendu (AAAA-MM-JJThh:mm:ssZ)")
        for valeur, champ, borne in ((lat, "lat", 90), (lon, "lon", 180)):
            if not DECIMAL.match(valeur) or abs(float(valeur)) > borne:
                err(n, f"{champ} « {valeur} » : degrés décimaux WGS84 attendus (point décimal)")
        if not DECIMAL.match(alt):
            err(n, f"altitude_rel_m « {alt} » : nombre décimal attendu")
        if not DECIMAL.match(cap) or not 0 <= float(cap) < 360:
            err(n, f"cap_deg « {cap} » : nombre dans [0, 360[ attendu")
        if not ENTIER.match(wp):
            err(n, f"index_waypoint « {wp} » : entier attendu")
        elif nb_wp is not None and int(wp) >= nb_wp:
            err(n, f"index_waypoint {wp} hors de la mission ({nb_wp} waypoints)")
        if not ENTIER.match(idm):
            err(n, f"id_mission « {idm} » : entier attendu")
        ids.add(idm)
    if len(ids) > 1:
        erreurs.append(f"{nom} : plusieurs id_mission dans un même vol ({', '.join(sorted(ids))}) "
                       f"[module fautif : {MODULE}]")
    if mission and ids and ids != {str(mission.get("idMission"))}:
        erreurs.append(f"{nom} : id_mission {', '.join(sorted(ids))} différent de la mission "
                       f"{mission.get('idMission')} [module fautif : {MODULE} ou planificateur]")
    return fichiers


def verifier_boite_noire(chemin: Path, erreurs: list[str]) -> int:
    lignes = lire_lignes(chemin, erreurs)
    if lignes is None:
        return 0
    nom = chemin.name
    def err(n: int, texte: str) -> None:
        erreurs.append(f"{nom}, ligne {n} : {texte} [module fautif : {MODULE}]")
    if not lignes or lignes[0] != ENTETE_BOITE_NOIRE:
        err(1, f"en-tête attendu « {ENTETE_BOITE_NOIRE} »")
        return 0
    for n, ligne in enumerate(lignes[1:], start=2):
        c = ligne.split(";")
        if len(c) != 11:
            err(n, f"{len(c)} colonnes au lieu de 11")
            continue
        heure, temps, source, categorie, code, nom_ev, gravite, action, valeur, actif, _ = c
        if heure and not HORODATAGE.match(heure):
            err(n, f"horodatage_utc « {heure} » invalide (vide autorisé avant l'heure GPS)")
        if not ENTIER.match(temps):
            err(n, f"temps_ms « {temps} » : entier attendu")
        if source not in SOURCES:
            err(n, f"source « {source} » inconnue")
        if categorie not in CATEGORIES:
            err(n, f"categorie « {categorie} » inconnue")
        if not re.match(r"^0x[0-9A-F]{2}$", code):
            err(n, f"code « {code} » : 0xHH attendu")
        if not nom_ev:
            err(n, "nom vide")
        if gravite not in GRAVITES:
            err(n, f"gravite « {gravite} » inconnue")
        if action not in ACTIONS:
            err(n, f"action « {action} » inconnue")
        if not re.match(r"^-?\d+$", valeur):
            err(n, f"valeur « {valeur} » : entier attendu")
        if actif not in ("", "0", "1"):
            err(n, f"actif « {actif} » : 0, 1 ou vide")
    return len(lignes) - 1


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("dossier", type=Path)
    a.add_argument("--mission", type=Path, help="fichier mission_<id>.json archivé par le planificateur")
    args = a.parse_args()

    erreurs: list[str] = []
    mission = None
    if args.mission:
        try:
            mission = json.loads(args.mission.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            erreurs.append(f"{args.mission.name} : illisible ({e}) [module fautif : planificateur]")

    fichiers = verifier_photos(args.dossier / "photos.csv", erreurs, mission)
    nb_evenements = verifier_boite_noire(args.dossier / "boite_noire.csv", erreurs)

    images = args.dossier / "images"
    if images.is_dir():
        presentes = {p.name for p in images.iterdir() if p.is_file()}
        for f in sorted(set(fichiers) - presentes):
            erreurs.append(f"photos.csv : « {f} » décrite mais absente de images/ "
                           f"[module fautif : caméra ou transfert Wi-Fi]")
        for f in sorted(presentes - set(fichiers)):
            erreurs.append(f"images/{f} : aucune ligne dans photos.csv [module fautif : {MODULE}]")

    if erreurs:
        print(f"{len(erreurs)} erreur(s) :")
        for e in erreurs:
            print(f"  - {e}")
        return 1
    print(f"Conforme : {len(fichiers)} photo(s), {nb_evenements} événement(s) dans la boîte noire.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
