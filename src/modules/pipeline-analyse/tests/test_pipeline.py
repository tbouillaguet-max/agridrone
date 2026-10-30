"""Tests de bout en bout et des contrôles d'entrée (une erreur = un test)."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from analyse import ErreurPipeline, executer
from conftest import ICI, ecrire_mission, lire_mission, options

VOL = Path("vols") / "entrant" / "mission_09001_01"


def _erreurs(opts) -> list[str]:
    with pytest.raises(ErreurPipeline) as e:
        executer(opts)
    return e.value.messages


# ------------------------------------------------------------------ bout en bout
def test_vol_demo_complet(demo):
    bilan = executer(options(demo))
    s = bilan.dossier_resultats
    assert s.name == "2026-11-02_9001"
    for f in ("rapport.html", "journal_pipeline.txt", "resultats/images.csv", "resultats/detections.csv",
              "resultats/zones_malades.geojson", "a_relabelliser/a_relabelliser.csv",
              "brut/photos.csv", "brut/boite_noire.csv", "brut/mission_9001.json"):
        assert (s / f).is_file(), f
    assert bilan.nb_images == 104
    assert 5 <= bilan.nb_malades <= 40

    lignes = list(csv.DictReader(open(s / "resultats/images.csv", encoding="utf-8"), delimiter=";"))
    assert len(lignes) == 104 and {l["statut"] for l in lignes} == {"sain", "malade"}
    zones = json.loads((s / "resultats/zones_malades.geojson").read_text(encoding="utf-8"))
    assert zones["features"] and all(f["properties"]["nb_malades"] >= 1 for f in zones["features"])

    # top : au plus 10 ; à relabelliser : 10 images copiées + CSV
    rel = list((s / "a_relabelliser").glob("*.JPG"))
    assert len(rel) == 10
    page = (s / "rapport.html").read_text(encoding="utf-8")
    assert "Modèle factice" in page and "BATTERIE_FAIBLE" in page and "Les 10 images malades les plus sûres" in page


def test_brut_en_lecture_seule_et_entrant_intact(demo):
    avant = sorted(p.name for p in (demo / VOL / "images").iterdir())
    s = executer(options(demo)).dossier_resultats
    assert sorted(p.name for p in (demo / VOL / "images").iterdir()) == avant
    assert not os.access(s / "brut" / "photos.csv", os.W_OK) or os.name == "nt" or os.geteuid() == 0


def test_jamais_d_ecrasement(demo):
    a = executer(options(demo)).dossier_resultats
    b = executer(options(demo)).dossier_resultats
    assert a != b and b.name == "2026-11-02_9001_2"


def test_moins_de_10_malades_on_les_met_toutes(demo):
    s = executer(options(demo, nb_top=1000)).dossier_resultats
    page = (s / "rapport.html").read_text(encoding="utf-8")
    assert "Toutes les images malades (" in page


def test_verifier_seulement_n_ecrit_rien(demo):
    executer(options(demo, verifier_seulement=True))
    assert not any(p.name.startswith("2026") for p in (demo / "vols").iterdir())


# ------------------------------------------------------------------ contrôles du vol (module fautif : drone / caméra)
def test_image_decrite_mais_absente(demo):
    (demo / VOL / "images" / "IMG_0003.JPG").unlink()
    m = _erreurs(options(demo))
    assert any("IMG_0003.JPG" in e and "caméra ou transfert" in e for e in m)
    assert list((demo / "vols" / "_echecs").glob("*.txt"))  # journal de l'échec conservé


def test_image_sans_ligne(demo):
    (demo / VOL / "images" / "IMG_9999.JPG").write_bytes((demo / VOL / "images" / "IMG_0001.JPG").read_bytes())
    assert any("IMG_9999.JPG" in e and "drone (AU2)" in e for e in _erreurs(options(demo)))


def test_image_illisible(demo):
    (demo / VOL / "images" / "IMG_0004.JPG").write_bytes(b"pas une image")
    assert any("IMG_0004.JPG" in e and "illisible" in e for e in _erreurs(options(demo)))


def test_entete_photos_incorrect(demo):
    p = demo / VOL / "photos.csv"
    p.write_text(p.read_text(encoding="utf-8").replace("cap_deg", "cap"), encoding="utf-8")
    assert any("photos.csv, ligne 1" in e for e in _erreurs(options(demo)))


def test_virgule_decimale_refusee(demo):
    p = demo / VOL / "photos.csv"
    lignes = p.read_text(encoding="utf-8").splitlines()
    c = lignes[5].split(";"); c[2] = c[2].replace(".", ","); lignes[5] = ";".join(c)
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    assert any("photos.csv, ligne 6" in e and "lat" in e for e in _erreurs(options(demo)))


def test_plusieurs_id_mission(demo):
    p = demo / VOL / "photos.csv"
    lignes = p.read_text(encoding="utf-8").splitlines()
    lignes[3] = lignes[3].rsplit(";", 1)[0] + ";12"
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    assert any("plusieurs id_mission" in e for e in _erreurs(options(demo)))


def test_boite_noire_absente_avertit(demo):
    (demo / VOL / "boite_noire.csv").unlink()
    bilan = executer(options(demo))  # facultative en v1
    assert any("boite_noire.csv absent" in a for a in bilan.avertissements)


def test_boite_noire_non_conforme(demo):
    p = demo / VOL / "boite_noire.csv"
    p.write_text(p.read_text(encoding="utf-8").replace(";CRITIQUE;", ";GRAVE;"), encoding="utf-8")
    assert any("boite_noire.csv, ligne" in e and "gravite" in e for e in _erreurs(options(demo)))


def test_bom_refuse(demo):
    p = demo / VOL / "photos.csv"
    p.write_bytes(b"\xef\xbb\xbf" + p.read_bytes())
    assert any("BOM" in e for e in _erreurs(options(demo)))


# ------------------------------------------------------------------ contrôles de la mission (module fautif : planificateur)
def test_mission_introuvable(demo):
    (demo / "missions" / "mission_9001.json").unlink()
    assert any("introuvable" in e and "planificateur" in e for e in _erreurs(options(demo)))


def test_mission_sans_culture(demo):
    m = lire_mission(demo); del m["culture"]; ecrire_mission(demo, m)
    assert any("culture" in e and "planificateur" in e for e in _erreurs(options(demo)))


def test_index_waypoint_hors_mission(demo):
    m = lire_mission(demo); m["waypoints"] = m["waypoints"][:3]; ecrire_mission(demo, m)
    assert any("index_waypoint" in e for e in _erreurs(options(demo)))


def test_mission_suffixe_choix_par_boite_noire(demo):
    """mission_9001_2.json (autre contenu, mauvais nombre de waypoints) est écartée."""
    m = lire_mission(demo)
    autre = dict(m, nom="autre mission", waypoints=m["waypoints"] + m["waypoints"][:2], modifieLe="2026-11-02T13:30:00Z")
    ecrire_mission(demo, autre, "mission_9001_2.json")
    bilan = executer(options(demo))
    assert (bilan.dossier_resultats / "brut" / "mission_9001.json").is_file()


def test_mission_suffixe_choix_par_date(demo):
    """Même nombre de waypoints : la plus récente avant le vol est retenue."""
    m = lire_mission(demo)
    ecrire_mission(demo, dict(m, nom="version corrigée", modifieLe="2026-11-02T13:50:00Z"), "mission_9001_2.json")
    ecrire_mission(demo, dict(m, nom="future", modifieLe="2026-11-03T09:00:00Z"), "mission_9001_3.json")
    bilan = executer(options(demo))
    assert (bilan.dossier_resultats / "brut" / "mission_9001_2.json").is_file()


def test_mission_ambigue_demande_option(demo):
    m = lire_mission(demo)
    for n in ("mission_9001.json", "mission_9001_2.json"):
        ecrire_mission(demo, dict(m, nom=n, modifieLe=None), n)
    assert any("--mission" in e for e in _erreurs(options(demo)))
    p = demo / "missions" / "mission_9001_2.json"
    bilan = executer(options(demo, mission_forcee=p))
    assert (bilan.dossier_resultats / "brut" / "mission_9001_2.json").is_file()


def test_photos_hors_limites_avertissement(demo):
    m = lire_mission(demo)
    m["limites"] = [[lat, lon] for lat, lon in m["limites"]]
    m["limites"][2][0] -= 0.00015  # rogne la parcelle
    ecrire_mission(demo, m)
    bilan = executer(options(demo))
    assert any("hors des limites" in a for a in bilan.avertissements)


# ------------------------------------------------------------------ registre des modèles
def test_modele_a_definir(demo):
    m = _erreurs(options(demo, registre=ICI / "modeles.json"))
    assert any("aucun modèle désigné" in e and "registre" in e for e in m)
    assert not any(p.name.startswith("2026") for p in (demo / "vols").iterdir())  # rien d'écrit


def test_onnx_introuvable(demo, tmp_path):
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"version": 1, "cultures": {c: {"type": "classification", "onnx": "absent.onnx",
                    "classes": ["sain", "malade"]} for c in ("ble", "mais", "pommier")}}), encoding="utf-8")
    assert any("ONNX introuvable" in e for e in _erreurs(options(demo, registre=reg)))
