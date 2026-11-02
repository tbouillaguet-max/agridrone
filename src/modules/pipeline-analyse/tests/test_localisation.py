"""Localisation : géométrie de la projection v2, précision sur le vol de démo, choix du mode."""
from __future__ import annotations

import csv
import json
import math

import pytest

import creer_vol_demo as demo_mod
from analyse import ErreurPipeline, executer
from analyse.geo import Camera, Prise, cellules_d_une_boite
from conftest import ecrire_mission, lire_mission, options

CAM = Camera(7.2, 5.4, 5.4, provisoire=True)  # emprise 13,33 × 10 m à 10 m


def _prise(cap: float) -> Prise:
    return Prise("IMG", 100.0, 50.0, 10.0, cap, 800, 600)


@pytest.mark.parametrize("cap", [0, 37.5, 90, 180, 271.3])
def test_aller_retour_pixel_sol(cap):
    p = _prise(cap)
    for u, v in ((0, 0), (800, 600), (123.4, 456.7), (400, 300)):
        x, y = p.pixel_vers_sol(u, v, CAM)
        assert p.sol_vers_pixel(x, y, CAM) == pytest.approx((u, v), abs=1e-6)


def test_haut_de_l_image_est_l_avant_du_drone():
    # centre -> position du drone ; haut de l'image (v = 0) -> 5 m devant
    assert _prise(0).pixel_vers_sol(400, 300, CAM) == pytest.approx((100, 50))
    assert _prise(0).pixel_vers_sol(400, 0, CAM) == pytest.approx((100, 55))      # cap nord : vers le nord
    assert _prise(90).pixel_vers_sol(400, 0, CAM) == pytest.approx((105, 50))     # cap est : vers l'est
    assert _prise(90).pixel_vers_sol(800, 300, CAM) == pytest.approx((100, 50 - 20 / 3))  # droite = sud


def test_couverture_et_cases_d_une_boite():
    p = _prise(0)
    assert p.couvre(106, 54, CAM) and not p.couvre(107, 50, CAM)
    cases = cellules_d_une_boite(p, (0, 0, 800, 600), CAM, 2.0)   # photo entière : ≈ 6 × 5 cases
    assert 25 <= len(cases) <= 42
    assert len(cellules_d_une_boite(p, (399, 299, 401, 301), CAM, 2.0)) == 1   # petite boîte : sa case


def _marge_foyer(lat: float, lon: float) -> float:
    k = math.cos(math.radians(demo_mod.LAT0))
    x = math.radians(lon - demo_mod.LON0) * 6_371_000 * k
    y = math.radians(lat - demo_mod.LAT0) * 6_371_000
    return min(math.hypot(x - fx, y - fy) - r for fx, fy, r in demo_mod.FOYERS)


def test_v2_par_defaut_et_precise(demo):
    bilan = executer(options(demo))
    s = bilan.dossier_resultats
    zones = json.loads((s / "resultats/zones_malades.geojson").read_text(encoding="utf-8"))
    assert zones["properties"] == {"cote_cellule_m": 2.0, "localisation": "v2 projection des détections"}
    dets = list(csv.DictReader(open(s / "resultats/detections.csv", encoding="utf-8"), delimiter=";"))
    assert dets and {d["localisation"] for d in dets} == {"v2"}
    # bruit GPS ±0,4 m et cap ±1,5° dans la démo : chaque détection tombe dans un foyer (à 1 m près)
    assert max(_marge_foyer(float(d["lat"]), float(d["lon"])) for d in dets) < 1.0
    for f in zones["features"]:
        p = f["properties"]
        assert 1 <= p["nb_malades"] <= p["nb_images"] and p["nb_detections"] >= p["nb_malades"]
    assert any("caméra non confirmée" in a for a in bilan.avertissements)
    assert "Détections" in (s / "rapport.html").read_text(encoding="utf-8")


def test_v1_forcee(demo):
    s = executer(options(demo, localisation="v1")).dossier_resultats
    zones = json.loads((s / "resultats/zones_malades.geojson").read_text(encoding="utf-8"))
    assert zones["properties"]["localisation"] == "v1 centre de photo"
    assert zones["properties"]["cote_cellule_m"] == 10.0


def test_camera_confirmee_sans_avertissement(demo):
    m = lire_mission(demo); m["camera"]["provisoire"] = False; ecrire_mission(demo, m)
    bilan = executer(options(demo))
    assert not any("caméra non confirmée" in a for a in bilan.avertissements)


def test_camera_absente_auto_v1_et_v2_forcee_refusee(demo):
    m = lire_mission(demo); del m["camera"]; ecrire_mission(demo, m)
    bilan = executer(options(demo))
    assert any("localisation v1" in a for a in bilan.avertissements)
    with pytest.raises(ErreurPipeline) as e:
        executer(options(demo, localisation="v2"))
    assert any("v2 impossible" in x and "planificateur" in x for x in e.value.messages)


def test_format_image_incoherent_avec_le_capteur(demo):
    m = lire_mission(demo); m["camera"]["capteurHauteurMm"] = 7.2; ecrire_mission(demo, m)  # capteur carré
    bilan = executer(options(demo))
    assert any("format ne correspond pas au capteur" in a for a in bilan.avertissements)


def test_mode_inconnu(demo):
    with pytest.raises(ErreurPipeline):
        executer(options(demo, localisation="v3"))
