"""Étape 1a — lecture et validation des fichiers du vol (contrat AU2, SPECIFICATION.md § 12).

Toutes les erreurs sont collectées (on ne s'arrête pas à la première) puis
renvoyées ensemble ; l'appelant décide d'arrêter le pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import contrat as C
from .contrat import erreur


@dataclass
class Photo:
    fichier: str
    horodatage: datetime
    lat: float
    lon: float
    altitude_rel_m: float
    cap_deg: float
    index_waypoint: int
    id_mission: int
    ligne: int


@dataclass
class Evenement:
    horodatage: datetime | None
    temps_ms: int
    source: str
    categorie: str
    code: str
    nom: str
    gravite: str
    action: str
    valeur: int
    actif: str
    detail: str
    ligne: int


@dataclass
class Vol:
    dossier: Path
    photos: list[Photo] = field(default_factory=list)
    evenements: list[Evenement] = field(default_factory=list)

    @property
    def id_mission(self) -> int | None:
        ids = {p.id_mission for p in self.photos}
        return ids.pop() if len(ids) == 1 else None

    @property
    def debut(self) -> datetime | None:
        return min((p.horodatage for p in self.photos), default=None)

    def chemin_image(self, photo: Photo) -> Path:
        return self.dossier / C.DOSSIER_IMAGES / photo.fichier


def _heure(texte: str) -> datetime:
    return datetime.strptime(texte, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _lire_lignes(chemin: Path, erreurs: list[str]) -> list[str] | None:
    try:
        octets = chemin.read_bytes()
    except FileNotFoundError:
        erreurs.append(erreur(chemin.name, "fichier absent du dossier du vol", C.MODULE_DRONE))
        return None
    if octets.startswith(b"\xef\xbb\xbf"):
        erreurs.append(erreur(chemin.name, "marque BOM interdite (UTF-8 sans BOM)", C.MODULE_DRONE))
        octets = octets[3:]
    try:
        texte = octets.decode("utf-8")
    except UnicodeDecodeError as e:
        erreurs.append(erreur(chemin.name, f"pas en UTF-8 ({e})", C.MODULE_DRONE))
        return None
    return [l.rstrip("\r") for l in texte.split("\n") if l.strip()]


def lire_photos(chemin: Path, erreurs: list[str]) -> list[Photo]:
    lignes = _lire_lignes(chemin, erreurs)
    if lignes is None:
        return []
    nom = chemin.name

    def err(n: int, texte: str) -> None:
        erreurs.append(erreur(nom, texte, C.MODULE_DRONE, n))

    if not lignes or lignes[0] != C.ENTETE_PHOTOS:
        err(1, f"en-tête attendu « {C.ENTETE_PHOTOS} », lu « {lignes[0] if lignes else ''} »")
        return []
    if len(lignes) == 1:
        erreurs.append(erreur(nom, "aucune photo décrite", C.MODULE_DRONE))
    photos: list[Photo] = []
    vus: set[str] = set()
    for n, ligne in enumerate(lignes[1:], start=2):
        c = ligne.split(";")
        if len(c) != 8:
            err(n, f"{len(c)} colonnes au lieu de 8")
            continue
        fichier, heure, lat, lon, alt, cap, wp, idm = c
        ok = True
        if not fichier:
            err(n, "nom de fichier vide"); ok = False
        elif fichier in vus:
            err(n, f"photo « {fichier} » déjà décrite"); ok = False
        vus.add(fichier)
        if not C.HORODATAGE.match(heure):
            err(n, f"horodatage_utc « {heure} » : ISO 8601 UTC attendu (AAAA-MM-JJThh:mm:ssZ)"); ok = False
        for valeur, champ, borne in ((lat, "lat", 90), (lon, "lon", 180)):
            if not C.DECIMAL.match(valeur) or abs(float(valeur)) > borne:
                err(n, f"{champ} « {valeur} » : degrés décimaux WGS84 attendus (point décimal)"); ok = False
        if not C.DECIMAL.match(alt):
            err(n, f"altitude_rel_m « {alt} » : nombre décimal attendu"); ok = False
        if not C.DECIMAL.match(cap) or not 0 <= float(cap) < 360:
            err(n, f"cap_deg « {cap} » : nombre dans [0, 360[ attendu"); ok = False
        if not C.ENTIER.match(wp):
            err(n, f"index_waypoint « {wp} » : entier attendu"); ok = False
        if not C.ENTIER.match(idm):
            err(n, f"id_mission « {idm} » : entier attendu"); ok = False
        if ok:
            photos.append(Photo(fichier, _heure(heure), float(lat), float(lon), float(alt),
                                float(cap), int(wp), int(idm), n))
    ids = sorted({p.id_mission for p in photos})
    if len(ids) > 1:
        erreurs.append(erreur(nom, f"plusieurs id_mission dans un même vol ({', '.join(map(str, ids))})",
                              C.MODULE_DRONE))
    return photos


def lire_boite_noire(chemin: Path, erreurs: list[str]) -> list[Evenement]:
    lignes = _lire_lignes(chemin, erreurs)
    if lignes is None:
        return []
    nom = chemin.name

    def err(n: int, texte: str) -> None:
        erreurs.append(erreur(nom, texte, C.MODULE_DRONE, n))

    if not lignes or lignes[0] != C.ENTETE_BOITE_NOIRE:
        err(1, f"en-tête attendu « {C.ENTETE_BOITE_NOIRE} »")
        return []
    evenements: list[Evenement] = []
    for n, ligne in enumerate(lignes[1:], start=2):
        c = ligne.split(";")
        if len(c) != 11:
            err(n, f"{len(c)} colonnes au lieu de 11")
            continue
        heure, temps, source, categorie, code, nom_ev, gravite, action, valeur, actif, detail = c
        avant = len(erreurs)
        if heure and not C.HORODATAGE.match(heure):
            err(n, f"horodatage_utc « {heure} » invalide (vide autorisé avant l'heure GPS)")
        if not C.ENTIER.match(temps):
            err(n, f"temps_ms « {temps} » : entier attendu")
        if source not in C.SOURCES:
            err(n, f"source « {source} » inconnue")
        if categorie not in C.CATEGORIES:
            err(n, f"categorie « {categorie} » inconnue")
        if not C.CODE_HEX.match(code):
            err(n, f"code « {code} » : 0xHH attendu")
        if not nom_ev:
            err(n, "nom vide")
        if gravite not in C.GRAVITES:
            err(n, f"gravite « {gravite} » inconnue")
        if action not in C.ACTIONS:
            err(n, f"action « {action} » inconnue")
        if not (valeur.lstrip("-").isdigit()):
            err(n, f"valeur « {valeur} » : entier attendu")
        if actif not in ("", "0", "1"):
            err(n, f"actif « {actif} » : 0, 1 ou vide")
        if len(erreurs) == avant:
            evenements.append(Evenement(_heure(heure) if heure else None, int(temps), source, categorie,
                                        code, nom_ev, gravite, action, int(valeur), actif, detail, n))
    return evenements


def verifier_images(vol: Vol, erreurs: list[str]) -> None:
    """Chaque photo décrite existe et est une image lisible ; chaque image a sa ligne."""
    dossier = vol.dossier / C.DOSSIER_IMAGES
    if not dossier.is_dir():
        erreurs.append(erreur(f"{C.DOSSIER_IMAGES}/", "dossier des images absent", C.MODULE_CAMERA))
        return
    presentes = {p.name for p in dossier.iterdir() if p.is_file()}
    decrites = {p.fichier for p in vol.photos}
    for f in sorted(decrites - presentes):
        erreurs.append(erreur(C.FICHIER_PHOTOS, f"« {f} » décrite mais absente de images/", C.MODULE_CAMERA))
    for f in sorted(presentes - decrites):
        erreurs.append(erreur(f"images/{f}", "aucune ligne dans photos.csv", C.MODULE_DRONE))
    for p in vol.photos:
        if p.fichier not in presentes:
            continue
        try:
            with Image.open(dossier / p.fichier) as im:
                im.verify()
        except Exception as e:  # image tronquée, mauvais format…
            erreurs.append(erreur(f"images/{p.fichier}", f"image illisible ({e.__class__.__name__}: {e})",
                                  C.MODULE_CAMERA))


def lire_vol(dossier: Path) -> tuple[Vol, list[str], list[str]]:
    """Lit et contrôle un dossier de vol. Renvoie (vol, erreurs, avertissements).

    La boîte noire est facultative en v1 : son absence est un avertissement ;
    si elle est présente, elle doit respecter le contrat.
    """
    erreurs: list[str] = []
    avert: list[str] = []
    if not dossier.is_dir():
        return Vol(dossier), [erreur(str(dossier), "dossier du vol introuvable", C.MODULE_CAMERA)], avert
    vol = Vol(dossier)
    vol.photos = lire_photos(dossier / C.FICHIER_PHOTOS, erreurs)
    if (dossier / C.FICHIER_BOITE_NOIRE).is_file():
        vol.evenements = lire_boite_noire(dossier / C.FICHIER_BOITE_NOIRE, erreurs)
    else:
        avert.append(f"{C.FICHIER_BOITE_NOIRE} absent : aucun événement de vol dans le rapport "
                     f"[module : {C.MODULE_DRONE}]")
    if vol.photos:
        verifier_images(vol, erreurs)
    return vol, erreurs, avert
