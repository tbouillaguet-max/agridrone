"""Étape 1b — choix et contrôle de la mission archivée par le planificateur.

Le planificateur archive chaque mission dans ``data\\missions\\mission_<id>.json``.
Si l'identifiant existe déjà avec un autre contenu, il écrit ``mission_<id>_2.json``,
``_3``… Le pipeline choisit alors le bon fichier ainsi :

  1. candidats = ``mission_<id>.json`` et ``mission_<id>_N.json`` valides ;
  2. on garde ceux qui ont au moins ``max(index_waypoint) + 1`` waypoints ;
  3. si la boîte noire contient « MISSION_CHARGEE … mission <id>, <n> waypoints »,
     on garde ceux qui ont exactement n waypoints ;
  4. parmi les restants, celui dont ``modifieLe`` est le plus récent sans dépasser
     le début du vol (+ tolérance d'horloge) ;
  5. s'il reste une ambiguïté : erreur, et l'opérateur précise ``--mission``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import contrat as C
from .contrat import erreur
from .vol import Vol


@dataclass
class Mission:
    chemin: Path
    donnees: dict

    @property
    def id(self) -> int:
        return int(self.donnees["idMission"])

    @property
    def culture(self) -> str:
        return self.donnees["culture"]

    @property
    def nom(self) -> str:
        return str(self.donnees.get("nom") or f"mission {self.id}")

    @property
    def limites(self) -> list[list[float]]:
        return self.donnees.get("limites") or []

    @property
    def zones(self) -> list[list[list[float]]]:
        return self.donnees.get("zones") or []

    @property
    def waypoints(self) -> list[dict]:
        return self.donnees.get("waypoints") or []

    @property
    def camera(self) -> dict:
        return self.donnees.get("camera") or {}

    @property
    def modifie_le(self) -> datetime | None:
        return _date_iso(self.donnees.get("modifieLe"))


def _date_iso(texte) -> datetime | None:
    if not isinstance(texte, str):
        return None
    try:
        d = datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _point(p) -> bool:
    return (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)
            and abs(p[0]) <= 90 and abs(p[1]) <= 180)


def controler_mission(chemin: Path, donnees) -> list[str]:
    """Contrôle d'une mission archivée (sortie du planificateur, entrée E3)."""
    nom = chemin.name
    m = C.MODULE_PLANIFICATEUR
    if not isinstance(donnees, dict):
        return [erreur(nom, "le fichier ne contient pas un objet JSON", m)]
    e: list[str] = []
    if donnees.get("version") != C.VERSION_MISSION:
        e.append(erreur(nom, f"version {donnees.get('version')!r} non prise en charge (attendu {C.VERSION_MISSION})", m))
    if not isinstance(donnees.get("idMission"), int):
        e.append(erreur(nom, "idMission absent ou non entier", m))
    culture = donnees.get("culture")
    if culture not in C.CULTURES:
        e.append(erreur(nom, f"culture {culture!r} absente ou inconnue (attendu : {', '.join(C.CULTURES)})", m))
    limites = donnees.get("limites")
    if not isinstance(limites, list) or len(limites) < 3 or not all(map(_point, limites)):
        e.append(erreur(nom, "limites absentes ou invalides (au moins 3 sommets [lat, lon])", m))
    zones = donnees.get("zones", [])
    if not isinstance(zones, list) or not all(isinstance(z, list) and all(map(_point, z)) for z in zones):
        e.append(erreur(nom, "zones interdites invalides", m))
    wps = donnees.get("waypoints")
    if not isinstance(wps, list) or not wps or not all(
            isinstance(w, dict) and _point([w.get("lat"), w.get("lon")]) for w in wps):
        e.append(erreur(nom, "waypoints absents ou invalides", m))
    return e


def _candidats(dossier: Path, id_mission: int) -> list[Path]:
    motif = re.compile(C.MOTIF_FICHIER_MISSION.format(id=id_mission))
    if not dossier.is_dir():
        return []
    def rang(p: Path) -> int:
        g = motif.match(p.name).group(2)
        return int(g) if g else 1
    return sorted((p for p in dossier.glob(f"mission_{id_mission}*.json") if motif.match(p.name)), key=rang)


def _charger(chemin: Path) -> tuple[Mission | None, list[str]]:
    try:
        donnees = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as ex:
        return None, [erreur(chemin.name, f"illisible ({ex})", C.MODULE_PLANIFICATEUR)]
    e = controler_mission(chemin, donnees)
    return (None, e) if e else (Mission(chemin, donnees), [])


def choisir_mission(vol: Vol, dossier_missions: Path, forcee: Path | None = None
                    ) -> tuple[Mission | None, list[str], list[str]]:
    """Renvoie (mission, erreurs, avertissements)."""
    avert: list[str] = []
    id_vol = vol.id_mission
    if id_vol is None:
        return None, [], []  # erreur déjà signalée par la lecture du vol

    if forcee is not None:
        mission, e = _charger(forcee)
        if mission and mission.id != id_vol:
            e.append(erreur(forcee.name, f"idMission {mission.id} différent de l'id_mission du vol ({id_vol})",
                            f"{C.MODULE_DRONE} ou {C.MODULE_PLANIFICATEUR}"))
        if mission and not e:
            e += _coherence_waypoints(mission, vol)
        return (mission if not e else None), e, avert

    chemins = _candidats(dossier_missions, id_vol)
    if not chemins:
        return None, [erreur(str(dossier_missions / f"mission_{id_vol}.json"),
                             f"mission {id_vol} introuvable dans les missions archivées",
                             f"{C.MODULE_PLANIFICATEUR} (archivage)")], avert

    valides: list[Mission] = []
    rejets: list[str] = []
    for p in chemins:
        m, e = _charger(p)
        if m and m.id != id_vol:
            e = [erreur(p.name, f"idMission {m.id} différent du nom du fichier", C.MODULE_PLANIFICATEUR)]
            m = None
        if m:
            valides.append(m)
        else:
            rejets += e
    if not valides:
        return None, rejets, avert
    if rejets:
        avert += [f"mission écartée : {r}" for r in rejets]

    max_wp = max(p.index_waypoint for p in vol.photos)
    restants = [m for m in valides if len(m.waypoints) > max_wp]
    if not restants:
        return None, [erreur(C.FICHIER_PHOTOS, f"index_waypoint {max_wp} incompatible avec toutes les missions "
                             f"{id_vol} archivées ({', '.join(m.chemin.name for m in valides)})",
                             f"{C.MODULE_DRONE} ou {C.MODULE_PLANIFICATEUR}")], avert

    nb_wp_bn = _waypoints_boite_noire(vol, id_vol)
    if nb_wp_bn is not None:
        filtres = [m for m in restants if len(m.waypoints) == nb_wp_bn]
        if filtres:
            restants = filtres
        else:
            avert.append(f"boîte noire : mission {id_vol} chargée avec {nb_wp_bn} waypoints, "
                         "aucune mission archivée n'a ce nombre ; choix sur la date")

    if len(restants) > 1 and vol.debut is not None:
        limite = vol.debut + timedelta(seconds=C.TOLERANCE_HORLOGE_S)
        dates = [(m.modifie_le, m) for m in restants if m.modifie_le and m.modifie_le <= limite]
        if dates:
            dates.sort(key=lambda t: t[0])
            choisie = dates[-1][1]
            avert.append(f"plusieurs missions {id_vol} archivées : {choisie.chemin.name} retenue "
                         "(la plus récente avant le vol)")
            restants = [choisie]

    if len(restants) > 1:
        return None, [erreur(", ".join(m.chemin.name for m in restants),
                             "impossible de choisir la mission du vol ; relancer avec --mission <fichier>",
                             C.MODULE_PLANIFICATEUR)], avert
    mission = restants[0]
    return mission, _coherence_waypoints(mission, vol), avert


def _coherence_waypoints(mission: Mission, vol: Vol) -> list[str]:
    nb = len(mission.waypoints)
    return [erreur(C.FICHIER_PHOTOS, f"index_waypoint {p.index_waypoint} hors de la mission ({nb} waypoints)",
                   C.MODULE_DRONE, p.ligne) for p in vol.photos if p.index_waypoint >= nb]


def _waypoints_boite_noire(vol: Vol, id_mission: int) -> int | None:
    for ev in reversed(vol.evenements):
        if ev.nom == "MISSION_CHARGEE":
            m = C.MOTIF_MISSION_CHARGEE.search(ev.detail)
            if m and int(m.group(1)) == id_mission:
                return int(m.group(2))
    return None
