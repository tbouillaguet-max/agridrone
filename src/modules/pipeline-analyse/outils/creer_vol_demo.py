#!/usr/bin/env python3
"""Fabrique un vol de DÉMONSTRATION conforme aux contrats, pour essayer le pipeline sans drone.

Crée, dans un dossier séparé (par défaut pipeline\\demo, jamais dans les vraies missions) :
  demo\\missions\\mission_<id>.json                    (format du planificateur, avec culture)
  demo\\vols\\entrant\\mission_<id 5 ch.>_01\\images\\    (≈ 100 photos synthétiques 800 × 600)
  demo\\vols\\entrant\\mission_<id 5 ch.>_01\\photos.csv
  demo\\vols\\entrant\\mission_<id 5 ch.>_01\\boite_noire.csv

Parcelle de 60 × 40 m en Beauce, vol à 10 m, deux foyers « malades » (taches brunes)
que le modèle factice doit retrouver sur la carte. Les images sont orientées comme celles
du drone : haut de l'image = avant = cap (passes alternées vers l'est puis l'ouest).

Usage : python outils/creer_vol_demo.py [--racine DIR] [--id 9001] [--culture ble] [--alerte-critique]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

LAT0, LON0 = 48.3010, 1.6030
R = 6_371_000.0
K = math.cos(math.radians(LAT0))
LARGEUR_M, HAUTEUR_M = 60.0, 40.0
ALTITUDE = 10.0
CAMERA = {"capteurLargeurMm": 7.2, "capteurHauteurMm": 5.4, "focaleMm": 5.4, "imageLargeurPx": 4000,
          "imageHauteurPx": 3000, "intervalleMinS": 0.7, "expositionMinUs": 100}
EMPRISE = (ALTITUDE * 7.2 / 5.4, ALTITUDE * 5.4 / 5.4)  # 13,3 × 10 m
IMG_W, IMG_H = 800, 600
FOYERS = [(18.0, 12.0, 7.0), (46.0, 31.0, 4.5)]  # x, y (m, depuis le coin sud-ouest), rayon


def deg(x: float, y: float) -> list[float]:
    return [round(LAT0 + math.degrees(y / R), 7), round(LON0 + math.degrees(x / (R * K)), 7)]


def image_synthetique(xc: float, yc: float, cap: float, rnd: random.Random) -> Image.Image:
    """Vue verticale centrée sur (xc, yc), haut de l'image = avant du drone = cap (comme la vraie caméra) :
    rangs de culture verts + taches brunes des foyers."""
    px_m = IMG_W / EMPRISE[0]
    g = np.random.default_rng(rnd.randrange(1 << 30))
    base = np.zeros((IMG_H, IMG_W, 3), np.float32)
    base[..., 0], base[..., 1], base[..., 2] = 70, 125, 45
    lignes = (np.sin((np.arange(IMG_W) / px_m + xc) * 2 * math.pi / 0.25) > 0.2)[None, :, None]
    base += lignes * np.array([10, 25, 5], np.float32)
    base += g.normal(0, 12, base.shape)
    im = Image.fromarray(base.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    sa, ca = math.sin(math.radians(cap)), math.cos(math.radians(cap))
    demi_diag = math.hypot(*EMPRISE) / 2
    for fx, fy, r in FOYERS:
        if math.hypot(fx - xc, fy - yc) > demi_diag + r:
            continue
        for _ in range(int(14 * r * r)):  # densité de taches constante quel que soit le rayon
            a, rr = rnd.uniform(0, 2 * math.pi), r * math.sqrt(rnd.random())
            mx, my = fx + rr * math.cos(a), fy + rr * math.sin(a)
            e, n = mx - xc, my - yc                       # est, nord (m)
            dx, dy = e * ca - n * sa, e * sa + n * ca     # droite, avant du drone (m)
            u, v = IMG_W / 2 + dx * px_m, IMG_H / 2 - dy * px_m
            s = rnd.uniform(4, 11)
            teinte = (rnd.randint(140, 175), rnd.randint(95, 120), rnd.randint(40, 60))
            d.ellipse((u - s, v - s * 0.7, u + s, v + s * 0.7), fill=teinte)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def creer(racine: Path, id_mission: int, culture: str, alerte_critique: bool, graine: int = 7) -> Path:
    rnd = random.Random(graine)
    debut = datetime(2026, 11, 2, 14, 5, 0, tzinfo=timezone.utc)

    limites = [deg(0, 0), deg(LARGEUR_M, 0), deg(LARGEUR_M, HAUTEUR_M), deg(0, HAUTEUR_M)]
    zones = [[deg(28, 18), deg(31, 18), deg(31, 21), deg(28, 21)]]  # un poteau
    passes = [3.0 + 5.5 * k for k in range(7)]
    waypoints, prises = [], []
    for k, y in enumerate(passes):
        xa, xb = (2.0, 58.0) if k % 2 == 0 else (58.0, 2.0)
        for x, action in ((xa, 2), (xb, 3)):
            lat, lon = deg(x, y)
            waypoints.append({"lat": lat, "lon": lon, "altitudeM": ALTITUDE, "vitesseMs": 2, "action": action})
        n = 15
        for i in range(n):
            x = xa + (xb - xa) * i / (n - 1)
            if 27 <= x <= 32 and 17 <= y <= 22:
                continue  # le quadrillage contourne la zone interdite
            prises.append((x, y, len(waypoints) - 2, 90.0 if xb > xa else 270.0))

    mission = {
        "version": 1, "nom": "Démo — parcelle de blé (Beauce)",
        "creeLe": (debut - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        "modifieLe": (debut - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        "idMission": id_mission, "culture": culture, "limites": limites, "zones": zones,
        "depart": deg(-3, 1), "mode": "auto",
        "parametres": {"altitudeM": ALTITUDE, "vitesseMaxMs": 0, "recouvrementFrontalPct": 75,
                       "recouvrementLateralPct": 60, "capPassesDeg": 90, "margeLimitesM": 2, "margeZonesM": 1,
                       "grandCoteTransversal": False, "finMission": "retour", "vitesseManuelleMs": 2},
        "camera": CAMERA, "waypoints": waypoints,
    }
    (racine / "missions").mkdir(parents=True, exist_ok=True)
    (racine / "missions" / f"mission_{id_mission}.json").write_text(
        json.dumps(mission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    vol = racine / "vols" / "entrant" / f"mission_{id_mission:05d}_01"
    if vol.exists():
        shutil.rmtree(vol)
    (vol / "images").mkdir(parents=True)
    lignes = ["fichier;horodatage_utc;lat;lon;altitude_rel_m;cap_deg;index_waypoint;id_mission"]
    t = debut
    for n, (x, y, wp, cap) in enumerate(prises, 1):
        nom = f"IMG_{n:04d}.JPG"
        image_synthetique(x, y, cap, rnd).save(vol / "images" / nom, "JPEG", quality=85)
        jx, jy = rnd.gauss(0, 0.4), rnd.gauss(0, 0.4)  # bruit GPS
        lat, lon = deg(x + jx, y + jy)
        alt = ALTITUDE + rnd.gauss(0, 0.05)
        lignes.append(f"{nom};{t.strftime('%Y-%m-%dT%H:%M:%SZ')};{lat:.7f};{lon:.7f};{alt:.2f};"
                      f"{(cap + rnd.gauss(0, 1.5)) % 360:.1f};{wp};{id_mission}")
        t += timedelta(seconds=2)
    (vol / "photos.csv").write_text("\n".join(lignes) + "\n", encoding="utf-8")

    h = lambda s: (debut + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")
    duree = 2 * len(prises)
    bn = ["horodatage_utc;temps_ms;source;categorie;code;nom;gravite;action;valeur;actif;detail",
          ";1500;AU2;SYSTEME;0x00;DEMARRAGE;INFO;AUCUNE;0;;AU2 v1",
          f"{h(-60)};34210;AU2;MISSION;0x00;MISSION_CHARGEE;INFO;AUCUNE;0;;mission {id_mission}, {len(waypoints)} waypoints",
          f"{h(-20)};74000;AU1;MODE;0x07;ARMEMENT;INFO;AUCUNE;0;;décollage",
          f"{h(80)};174000;AU2;ALERTE;0x11;VENT_FORT;AVERTISSEMENT;POURSUITE;9;1;rafales 9 m/s"]
    if alerte_critique:
        bn.append(f"{h(duree - 10)};{94000 + duree * 1000};AU1;ALERTE;0x04;BATTERIE_FAIBLE;CRITIQUE;RETOUR_MAISON;139;1;13,9 V")
    bn.append(f"{h(duree + 40)};{134000 + duree * 1000};AU1;MODE;0x00;DESARMEMENT;INFO;AUCUNE;0;;posé depuis 3 s")
    (vol / "boite_noire.csv").write_text("\n".join(bn) + "\n", encoding="utf-8")
    return vol


def main() -> int:
    ici = Path(__file__).resolve().parents[1]
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("--racine", type=Path, default=ici / "demo")
    a.add_argument("--id", type=int, default=9001)
    a.add_argument("--culture", default="ble", choices=["ble", "mais", "pommier"])
    a.add_argument("--alerte-critique", action="store_true", help="ajoute une alerte batterie CRITIQUE")
    args = a.parse_args()
    vol = creer(args.racine.resolve(), args.id, args.culture, args.alerte_critique)
    print(f"Vol de démonstration créé : {vol}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
