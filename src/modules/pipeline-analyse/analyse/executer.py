"""Orchestration des étapes 1 à 6 du pipeline (l'étape 0, réception Wi-Fi, viendra plus tard)."""
from __future__ import annotations

import csv
import json
import os
import shutil
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

from . import contrat as C
from .contrat import ErreurPipeline
from .geo import (Prise, Projection, cote_grille, dans_polygone, geojson_zones, geojson_zones_v2, grille,
                  lire_camera)
from .mission import Mission, choisir_mission
from .modeles import ModeleCharge, ResultatImage, charger_modele
from .rapport import ecrire_rapport
from .vol import Photo, Vol, lire_vol


@dataclass
class Options:
    dossier_vol: Path
    dossier_missions: Path
    registre: Path
    dossier_sortie: Path
    mission_forcee: Path | None = None
    nb_top: int = C.NB_TOP_MALADES
    nb_incertaines: int = C.NB_INCERTAINES
    verifier_seulement: bool = False
    silencieux: bool = False
    localisation: str = "auto"  # auto (v2 si la mission donne la caméra, sinon v1) | v1 | v2


@dataclass
class AnalyseImage:
    photo: Photo
    resultat: ResultatImage | None
    dans_limites: bool
    erreur: str = ""
    taille: tuple[int, int] | None = None  # (largeur, hauteur) en pixels, après rotation EXIF

    @property
    def ecart_seuil(self) -> float:
        return abs(self.resultat.score - self._seuil) if self.resultat else 9.0

    _seuil: float = 0.5


@dataclass
class Bilan:
    """Ce que renvoie le pipeline (utilisé par les tests et, plus tard, par l'automatisation)."""
    dossier_resultats: Path | None = None
    rapport: Path | None = None
    nb_images: int = 0
    nb_malades: int = 0
    avertissements: list[str] = field(default_factory=list)


class Journal:
    def __init__(self, silencieux: bool):
        self.lignes: list[str] = []
        self.silencieux = silencieux

    def __call__(self, niveau: str, texte: str) -> None:
        ligne = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\t{niveau}\t{texte}"
        self.lignes.append(ligne)
        if not self.silencieux:
            print(f"[{niveau}] {texte}", flush=True)

    def ecrire(self, chemin: Path) -> None:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text("\n".join(self.lignes) + "\n", encoding="utf-8")


def _arreter(journal: Journal, opts: Options, etape: str, erreurs: list[str]) -> None:
    for e in erreurs:
        journal("ERREUR", e)
    journal("ERREUR", f"arrêt du pipeline à l'étape « {etape} » : rien n'a été analysé")
    if not opts.verifier_seulement:
        nom = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{opts.dossier_vol.name}.txt"
        journal.ecrire(opts.dossier_sortie / "_echecs" / nom)
    raise ErreurPipeline(etape, erreurs)


def _dossier_resultats(racine: Path, vol: Vol) -> Path:
    base = f"{vol.debut.strftime('%Y-%m-%d')}_{vol.id_mission}"
    chemin, n = racine / base, 2
    while chemin.exists():
        chemin = racine / f"{base}_{n}"
        n += 1
    return chemin


def _lecture_seule(dossier: Path) -> None:
    for p in dossier.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def _ecrire_csv(chemin: Path, entete: list[str], lignes: list[list]) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with open(chemin, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\n")
        w.writerow(entete)
        w.writerows(lignes)


def _fmt(v: float, n: int = 4) -> str:
    return f"{v:.{n}f}"


def executer(opts: Options) -> Bilan:
    journal = Journal(opts.silencieux)
    bilan = Bilan()
    debut = time.perf_counter()
    journal("INFO", f"pipeline d'analyse v{C.VERSION_PIPELINE} — vol : {opts.dossier_vol}")

    # 1. Validation ------------------------------------------------------------
    vol, erreurs, avert = lire_vol(opts.dossier_vol)
    for a in avert:
        journal("AVERT", a)
    bilan.avertissements += avert
    if erreurs:
        _arreter(journal, opts, "validation du vol", erreurs)
    journal("INFO", f"vol conforme : {len(vol.photos)} photo(s), {len(vol.evenements)} événement(s) "
                    f"dans la boîte noire, mission {vol.id_mission}")

    mission, erreurs, avert = choisir_mission(vol, opts.dossier_missions, opts.mission_forcee)
    for a in avert:
        journal("AVERT", a)
    bilan.avertissements += avert
    if erreurs or mission is None:
        _arreter(journal, opts, "choix de la mission", erreurs)
    journal("INFO", f"mission : {mission.chemin.name} — « {mission.nom} », culture "
                    f"{C.NOMS_CULTURES[mission.culture]}, {len(mission.waypoints)} waypoints")

    hors = [p for p in vol.photos if not dans_polygone(p.lat, p.lon, mission.limites)]
    if hors:
        a = (f"{len(hors)} photo(s) prise(s) hors des limites de la parcelle "
             f"({', '.join(p.fichier for p in hors[:5])}{'…' if len(hors) > 5 else ''})")
        journal("AVERT", a)
        bilan.avertissements.append(a)

    # 3. Choix du modèle (avant la sauvegarde : une config incomplète ne crée rien)
    modele, erreurs, avert = charger_modele(opts.registre, mission.culture)
    for a in avert:
        journal("AVERT", a)
    bilan.avertissements += avert
    if erreurs or modele is None:
        _arreter(journal, opts, "choix du modèle", erreurs)
    journal("INFO", f"modèle : {modele.type} ({modele.description or 'sans description'}), seuil {modele.seuil}")

    # 5a. Mode de localisation (décidé avant toute écriture)
    if opts.localisation not in C.MODES_LOCALISATION:
        _arreter(journal, opts, "choix de la localisation",
                 [C.erreur("--localisation", f"« {opts.localisation} » inconnu (attendu : "
                           f"{', '.join(C.MODES_LOCALISATION)})", C.MODULE_PIPELINE)])
    camera, raison = lire_camera(mission.camera)
    mode = opts.localisation
    if mode == "v2" and camera is None:
        _arreter(journal, opts, "choix de la localisation",
                 [C.erreur(mission.chemin.name, f"{raison} : localisation v2 impossible", C.MODULE_PLANIFICATEUR)])
    if mode == "auto":
        mode = "v2" if camera else "v1"
        if camera is None:
            a = f"{raison} : localisation v1 (centre des photos) à la place de la v2"
            journal("AVERT", a)
            bilan.avertissements.append(a)
    if mode == "v2" and camera.provisoire:
        a = ("caméra non confirmée par la mission (camera.provisoire différent de false) : positions v2 "
             "calculées avec des paramètres provisoires, à reprendre quand la caméra sera choisie")
        journal("AVERT", a)
        bilan.avertissements.append(a)
    journal("INFO", f"localisation : {mode}")

    if opts.verifier_seulement:
        journal("INFO", "vérification seule demandée : entrées conformes, aucune analyse lancée")
        return bilan

    # 2. Sauvegarde --------------------------------------------------------------
    sortie = _dossier_resultats(opts.dossier_sortie, vol)
    brut = sortie / "brut"
    shutil.copytree(vol.dossier, brut)
    shutil.copy2(mission.chemin, brut / mission.chemin.name)
    _lecture_seule(brut)
    journal("INFO", f"sauvegarde : {brut}")
    vol_brut = Vol(brut, vol.photos, vol.evenements)

    # 4. Analyse ML ---------------------------------------------------------------
    analyses: list[AnalyseImage] = []
    t0 = time.perf_counter()
    for k, p in enumerate(vol.photos, 1):
        dedans = p not in hors
        try:
            with Image.open(vol_brut.chemin_image(p)) as im:
                image = ImageOps.exif_transpose(im).convert("RGB")
            r = modele.analyser(image)
            a = AnalyseImage(p, r, dedans, taille=image.size)
        except Exception as ex:
            a = AnalyseImage(p, None, dedans, f"{ex.__class__.__name__}: {ex}")
            journal("AVERT", f"images/{p.fichier} : analyse impossible ({a.erreur})")
        a._seuil = modele.seuil
        analyses.append(a)
        if k % 20 == 0 or k == len(vol.photos):
            journal("INFO", f"analyse : {k}/{len(vol.photos)} image(s)")
    ok = [a for a in analyses if a.resultat]
    if not ok:
        _arreter(journal, opts, "analyse", [C.erreur(modele.culture, "aucune image n'a pu être analysée",
                                                     C.MODULE_REGISTRE)])
    if len(ok) < len(analyses):
        bilan.avertissements.append(f"{len(analyses) - len(ok)} image(s) non analysée(s) (voir le journal)")
    malades = [a for a in ok if a.resultat.malade]
    journal("INFO", f"analyse terminée en {time.perf_counter() - t0:.1f} s : {len(malades)} image(s) malade(s) "
                    f"sur {len(ok)}")

    # 5. Localisation 2D ------------------------------------------------------------
    lat0 = sum(p[0] for p in mission.limites) / len(mission.limites)
    lon0 = sum(p[1] for p in mission.limites) / len(mission.limites)
    proj = Projection(lat0, lon0)
    prises: dict[str, Prise] = {}
    for a in ok:
        x, y = proj.vers_m(a.photo.lat, a.photo.lon)
        prises[a.photo.fichier] = Prise(a.photo.fichier, x, y, a.photo.altitude_rel_m, a.photo.cap_deg, *a.taille)
    position_det: dict[int, tuple[float, float]] = {}  # id(detection) -> (lat, lon)

    if mode == "v2":
        cote = C.COTE_GRILLE_V2_M
        format_capteur = camera.largeur_mm / camera.hauteur_mm
        mauvais = [a.photo.fichier for a in ok
                   if abs(a.taille[0] / a.taille[1] - format_capteur) / format_capteur > C.ECART_FORMAT_IMAGE]
        if mauvais:
            av = (f"{len(mauvais)} image(s) dont le format ne correspond pas au capteur de la mission "
                  f"({', '.join(mauvais[:3])}{'…' if len(mauvais) > 3 else ''}) : positions v2 faussées "
                  "[module : planificateur (paramètres caméra) ou caméra]")
            journal("AVERT", av)
            bilan.avertissements.append(av)
        dets_sol = []
        for a in malades:
            pr = prises[a.photo.fichier]
            for d in a.resultat.detections:
                boite = d.boite or (0, 0, pr.largeur_px, pr.hauteur_px)  # image entière classée malade
                dets_sol.append((pr, boite, d.score))
                position_det[id(d)] = proj.vers_deg(*pr.pixel_vers_sol((boite[0] + boite[2]) / 2,
                                                                        (boite[1] + boite[3]) / 2, camera))
        zones = geojson_zones_v2(dets_sol, list(prises.values()), camera, proj, cote)
        alt = sorted(p.altitude_m for p in prises.values())[len(prises) // 2]
        L, H = camera.emprise(alt)
        explication = (f"v2 : chaque détection est projetée au sol (position, altitude, cap, caméra visée verticale, "
                       f"haut de l'image = avant du drone) ; emprise d'une photo ≈ {L:.1f} × {H:.1f} m à {alt:.1f} m ; "
                       f"grille de {cote:.0f} m" + (" ; caméra provisoire" if camera.provisoire else ""))
    else:
        cote, texte = cote_grille(mission.camera, [p.altitude_rel_m for p in vol.photos])
        cellules = grille([(a.photo.fichier, a.photo.lat, a.photo.lon, a.resultat.malade, a.resultat.score)
                           for a in ok], proj, cote)
        zones = geojson_zones(cellules, proj, cote)
        explication = f"v1 : chaque image est placée à la position du drone au moment de la photo ({texte})"
    journal("INFO", f"localisation {mode} : {len(zones['features'])} case(s) malade(s) de {cote:g} m")
    res = sortie / "resultats"
    res.mkdir(parents=True)
    (res / "zones_malades.geojson").write_text(json.dumps(zones, ensure_ascii=False, indent=1), encoding="utf-8")

    _ecrire_csv(res / "images.csv",
                ["fichier", "statut", "score", "nb_detections", "nb_elements", "horodatage_utc", "lat", "lon",
                 "altitude_rel_m", "cap_deg", "index_waypoint", "dans_limites", "remarque"],
                [[a.photo.fichier,
                  ("malade" if a.resultat.malade else "sain") if a.resultat else "erreur",
                  _fmt(a.resultat.score) if a.resultat else "",
                  len(a.resultat.detections) if a.resultat else "",
                  a.resultat.nb_elements if a.resultat else "",
                  a.photo.horodatage.strftime("%Y-%m-%dT%H:%M:%SZ"), f"{a.photo.lat:.7f}", f"{a.photo.lon:.7f}",
                  f"{a.photo.altitude_rel_m:.2f}", f"{a.photo.cap_deg:.1f}", a.photo.index_waypoint,
                  int(a.dans_limites), a.erreur or (a.resultat.remarque if a.resultat else "")]
                 for a in analyses])
    lignes_det, points = [], []
    for a in ok:
        for d in a.resultat.detections:
            lat, lon = position_det.get(id(d), (a.photo.lat, a.photo.lon))
            lignes_det.append([a.photo.fichier, d.classe, _fmt(d.score)]
                              + ([f"{v:.0f}" for v in d.boite] if d.boite else ["", "", "", ""])
                              + [f"{lat:.7f}", f"{lon:.7f}", mode])
            if mode == "v2":
                points.append({"f": a.photo.fichier, "lat": round(lat, 7), "lon": round(lon, 7),
                               "s": round(d.score, 3)})
    _ecrire_csv(res / "detections.csv",
                ["fichier", "classe", "score", "x1", "y1", "x2", "y2", "lat", "lon", "localisation"], lignes_det)

    # 6. Rapport + images à relabelliser ---------------------------------------------
    top = sorted(malades, key=lambda a: -a.resultat.score)[:opts.nb_top]
    incertaines = sorted(ok, key=lambda a: a.ecart_seuil)[:opts.nb_incertaines]
    rel = sortie / "a_relabelliser"
    rel.mkdir()
    for a in incertaines:
        shutil.copy2(vol_brut.chemin_image(a.photo), rel / a.photo.fichier)
        os.chmod(rel / a.photo.fichier, stat.S_IREAD | stat.S_IWRITE)
    _ecrire_csv(rel / "a_relabelliser.csv",
                ["rang", "fichier", "statut_predit", "score", "ecart_au_seuil", "lat", "lon", "label_corrige"],
                [[k, a.photo.fichier, "malade" if a.resultat.malade else "sain", _fmt(a.resultat.score),
                  _fmt(a.ecart_seuil), f"{a.photo.lat:.7f}", f"{a.photo.lon:.7f}", ""]
                 for k, a in enumerate(incertaines, 1)])

    alertes = [e for e in vol.evenements if e.gravite in C.GRAVITES_SIGNALEES]
    for e in alertes:
        a = f"boîte noire : {e.gravite} {e.source} {e.nom} ({e.detail or e.action})"
        journal("AVERT", a)
    bilan.rapport = ecrire_rapport(
        sortie / "rapport.html", vol=vol_brut, mission=mission, modele=modele, analyses=analyses,
        top=top, incertaines=incertaines, zones=zones, explication_grille=explication,
        localisation=mode, points_detections=points,
        avertissements=bilan.avertissements, nb_top=opts.nb_top)
    journal("INFO", f"rapport : {bilan.rapport}")
    journal("INFO", f"terminé en {time.perf_counter() - debut:.1f} s")
    journal.ecrire(sortie / "journal_pipeline.txt")

    bilan.dossier_resultats = sortie
    bilan.nb_images = len(ok)
    bilan.nb_malades = len(malades)
    return bilan
