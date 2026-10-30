"""Étape 5 — localisation 2D (v1 : position du drone = centre de la photo).

Projection locale équirectangulaire (précise au centimètre sur une parcelle) ;
grille carrée dont le côté vaut le petit côté de l'emprise d'une photo.
v2 (à venir) : projection de chaque détection au sol (altitude, cap, caméra), grille de 2 m.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from . import contrat as C

R_TERRE = 6_371_000.0


class Projection:
    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.k = math.cos(math.radians(lat0))

    def vers_m(self, lat: float, lon: float) -> tuple[float, float]:
        return (math.radians(lon - self.lon0) * R_TERRE * self.k, math.radians(lat - self.lat0) * R_TERRE)

    def vers_deg(self, x: float, y: float) -> tuple[float, float]:
        return (self.lat0 + math.degrees(y / R_TERRE), self.lon0 + math.degrees(x / (R_TERRE * self.k)))


def dans_polygone(lat: float, lon: float, poly: list[list[float]]) -> bool:
    dedans = False
    n = len(poly)
    for i in range(n):
        (y1, x1), (y2, x2) = poly[i], poly[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1:
            dedans = not dedans
    return dedans


def emprise_photo(camera: dict, altitude_m: float) -> tuple[float, float] | None:
    """Emprise au sol (largeur, hauteur) en mètres, caméra pointée vers le sol."""
    try:
        f = float(camera["focaleMm"])
        return (altitude_m * float(camera["capteurLargeurMm"]) / f, altitude_m * float(camera["capteurHauteurMm"]) / f)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


@dataclass
class Cellule:
    i: int
    j: int
    fichiers: list[str]
    malades: list[tuple[str, float]]


def grille(points: list[tuple[str, float, float, bool, float]], proj: Projection, cote_m: float
           ) -> dict[tuple[int, int], Cellule]:
    """points : (fichier, lat, lon, malade, score). Regroupe les photos par cellule."""
    cellules: dict[tuple[int, int], Cellule] = {}
    for fichier, lat, lon, malade, score in points:
        x, y = proj.vers_m(lat, lon)
        cle = (math.floor(x / cote_m), math.floor(y / cote_m))
        c = cellules.setdefault(cle, Cellule(cle[0], cle[1], [], []))
        c.fichiers.append(fichier)
        if malade:
            c.malades.append((fichier, score))
    return cellules


def geojson_zones(cellules: dict[tuple[int, int], Cellule], proj: Projection, cote_m: float) -> dict:
    """Cellules contenant au moins une image malade, en polygones lat/lon (GeoJSON : [lon, lat])."""
    feats = []
    for (i, j), c in sorted(cellules.items()):
        if not c.malades:
            continue
        coins = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1), (i, j)]
        anneau = []
        for a, b in coins:
            lat, lon = proj.vers_deg(a * cote_m, b * cote_m)
            anneau.append([round(lon, 7), round(lat, 7)])
        scores = [s for _, s in c.malades]
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [anneau]},
            "properties": {
                "nb_images": len(c.fichiers),
                "nb_malades": len(c.malades),
                "part_malades": round(len(c.malades) / len(c.fichiers), 3),
                "confiance_moyenne": round(sum(scores) / len(scores), 4),
                "confiance_max": round(max(scores), 4),
                "fichiers_malades": [f for f, _ in sorted(c.malades, key=lambda t: -t[1])],
            },
        })
    return {"type": "FeatureCollection", "name": "zones_malades",
            "properties": {"cote_cellule_m": round(cote_m, 2), "localisation": "v1 centre de photo"},
            "features": feats}


def cote_grille(camera: dict, altitudes: list[float]) -> tuple[float, str]:
    """Côté de la grille v1 et texte explicatif."""
    alt = sorted(altitudes)[len(altitudes) // 2] if altitudes else 0
    emp = emprise_photo(camera, alt) if alt > 0 else None
    if not emp:
        return C.COTE_GRILLE_DEFAUT_M, (f"paramètres caméra absents de la mission : grille de "
                                        f"{C.COTE_GRILLE_DEFAUT_M:.0f} m par défaut")
    cote = max(1.0, round(min(emp) * 2) / 2)
    return cote, (f"emprise d'une photo ≈ {emp[0]:.1f} × {emp[1]:.1f} m à {alt:.1f} m ; "
                  f"grille de {cote:.1f} m (petit côté de l'emprise)")


# ============================================================================ v2
# Projection de chaque détection au sol. Hypothèses (validées avec Tom) :
#   * caméra pointée verticalement vers le sol (nadir), modèle sténopé sans distorsion ;
#   * haut de l'image = avant du drone = cap_deg (0 = nord, sens horaire) ;
#   * sol plat à altitude_rel_m sous la caméra.
# Repère image : u vers la droite, v vers le bas (pixels). Repère sol : x = est, y = nord (m).

@dataclass
class Camera:
    largeur_mm: float
    hauteur_mm: float
    focale_mm: float
    provisoire: bool

    def emprise(self, altitude_m: float) -> tuple[float, float]:
        """(largeur, hauteur) au sol en mètres : largeur = travers du drone, hauteur = axe avant."""
        return altitude_m * self.largeur_mm / self.focale_mm, altitude_m * self.hauteur_mm / self.focale_mm


def lire_camera(camera: dict) -> tuple[Camera | None, str]:
    """Camera de la mission, ou (None, raison). `provisoire` vaut vrai sauf si la mission écrit `false`."""
    try:
        c = Camera(float(camera["capteurLargeurMm"]), float(camera["capteurHauteurMm"]),
                   float(camera["focaleMm"]), camera.get("provisoire", True) is not False)
    except (KeyError, TypeError, ValueError):
        return None, "paramètres caméra absents ou invalides dans la mission (capteurLargeurMm, capteurHauteurMm, focaleMm)"
    if min(c.largeur_mm, c.hauteur_mm, c.focale_mm) <= 0:
        return None, "paramètres caméra nuls ou négatifs dans la mission"
    return c, ""


@dataclass
class Prise:
    """Position et orientation d'une photo dans le repère local."""
    fichier: str
    x: float
    y: float
    altitude_m: float
    cap_deg: float
    largeur_px: int
    hauteur_px: int

    def _rot(self) -> tuple[float, float]:
        a = math.radians(self.cap_deg)
        return math.sin(a), math.cos(a)

    def pixel_vers_sol(self, u: float, v: float, cam: Camera) -> tuple[float, float]:
        L, H = cam.emprise(self.altitude_m)
        dx = (u / self.largeur_px - 0.5) * L      # vers la droite du drone
        dy = (0.5 - v / self.hauteur_px) * H      # vers l'avant du drone
        s, c = self._rot()
        return self.x + dx * c + dy * s, self.y - dx * s + dy * c

    def sol_vers_pixel(self, x: float, y: float, cam: Camera) -> tuple[float, float]:
        L, H = cam.emprise(self.altitude_m)
        s, c = self._rot()
        e, n = x - self.x, y - self.y
        dx, dy = e * c - n * s, e * s + n * c
        return (dx / L + 0.5) * self.largeur_px, (0.5 - dy / H) * self.hauteur_px

    def couvre(self, x: float, y: float, cam: Camera) -> bool:
        u, v = self.sol_vers_pixel(x, y, cam)
        return 0 <= u <= self.largeur_px and 0 <= v <= self.hauteur_px


def cellules_d_une_boite(prise: Prise, boite: tuple[float, float, float, float], cam: Camera,
                         cote: float) -> set[tuple[int, int]]:
    """Cases de la grille dont le centre tombe dans la boîte projetée au sol (+ la case du centre de la boîte)."""
    x1, y1, x2, y2 = boite
    coins = [prise.pixel_vers_sol(u, v, cam) for u, v in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
    xs, ys = [p[0] for p in coins], [p[1] for p in coins]
    cases = set()
    for i in range(math.floor(min(xs) / cote), math.floor(max(xs) / cote) + 1):
        for j in range(math.floor(min(ys) / cote), math.floor(max(ys) / cote) + 1):
            u, v = prise.sol_vers_pixel((i + 0.5) * cote, (j + 0.5) * cote, cam)
            if x1 <= u <= x2 and y1 <= v <= y2:
                cases.add((i, j))
    cx, cy = prise.pixel_vers_sol((x1 + x2) / 2, (y1 + y2) / 2, cam)
    cases.add((math.floor(cx / cote), math.floor(cy / cote)))
    return cases


def geojson_zones_v2(detections: list[tuple[Prise, tuple[float, float, float, float], float]],
                     prises: list[Prise], cam: Camera, proj: Projection, cote: float) -> dict:
    """detections : (prise, boîte en pixels, score). Une case est malade si une détection la recouvre ;
    nb_images = photos dont l'emprise couvre le centre de la case (permet de juger la confirmation)."""
    cases: dict[tuple[int, int], list[tuple[str, float]]] = defaultdict(list)
    for prise, boite, score in detections:
        for k in cellules_d_une_boite(prise, boite, cam, cote):
            cases[k].append((prise.fichier, score))
    feats = []
    for (i, j), dets in sorted(cases.items()):
        xc, yc = (i + 0.5) * cote, (j + 0.5) * cote
        couvrant = {p.fichier for p in prises if p.couvre(xc, yc, cam)}
        par_image: dict[str, float] = {}
        for f, s in dets:
            par_image[f] = max(s, par_image.get(f, 0.0))
        couvrant |= set(par_image)
        scores = [s for _, s in dets]
        anneau = []
        for a, b in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1), (i, j)):
            lat, lon = proj.vers_deg(a * cote, b * cote)
            anneau.append([round(lon, 7), round(lat, 7)])
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [anneau]},
            "properties": {
                "nb_images": len(couvrant),
                "nb_malades": len(par_image),
                "part_malades": round(len(par_image) / len(couvrant), 3),
                "nb_detections": len(dets),
                "confiance_moyenne": round(sum(scores) / len(scores), 4),
                "confiance_max": round(max(scores), 4),
                "fichiers_malades": [f for f, _ in sorted(par_image.items(), key=lambda t: -t[1])],
            },
        })
    return {"type": "FeatureCollection", "name": "zones_malades",
            "properties": {"cote_cellule_m": round(cote, 2), "localisation": "v2 projection des détections"},
            "features": feats}
