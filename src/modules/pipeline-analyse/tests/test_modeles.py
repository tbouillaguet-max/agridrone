"""Contrat d'inférence : vrai modèle ONNX (construit à la volée), décodage YOLO, deux étages."""
from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from analyse import executer
from analyse.modeles import ClassifieurTuiles, DeuxEtages, ResultatImage, decoder_yolov8, nms, _tuiles
from conftest import options

onnx = pytest.importorskip("onnx")
from onnx import TensorProto, helper  # noqa: E402


def _modele_rouge_vert(chemin):
    """Classifieur ONNX minimal : logits = 20 × [vert − rouge, rouge − vert] (moyennes de l'image)."""
    x = helper.make_tensor_value_info("image", TensorProto.FLOAT, [1, 3, 64, 64])
    y = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [1, 2])
    axes = helper.make_tensor("axes", TensorProto.INT64, [2], [2, 3])
    w = helper.make_tensor("w", TensorProto.FLOAT, [3, 2], [-20, 20, 20, -20, 0, 0])
    b = helper.make_tensor("b", TensorProto.FLOAT, [2], [0, 6.2])  # malade dès ≈ 15 % de taches brunes
    g = helper.make_graph([helper.make_node("ReduceMean", ["image", "axes"], ["m"], keepdims=0),
                           helper.make_node("MatMul", ["m", "w"], ["l"]),
                           helper.make_node("Add", ["l", "b"], ["logits"])],
                          "rouge_vert", [x], [y], [axes, w, b])
    m = helper.make_model(g, opset_imports=[helper.make_opsetid("", 18)])
    m.ir_version = 9
    onnx.save(m, chemin)


def test_classification_onnx_bout_en_bout(demo, tmp_path):
    _modele_rouge_vert(tmp_path / "rv.onnx")
    conf = {"type": "classification", "onnx": "rv.onnx", "description": "test ONNX", "classes": ["sain", "malade"],
            "classe_malade": "malade", "seuil": 0.4,
            "entree": {"largeur": 64, "hauteur": 64, "normalisation": "aucune", "disposition": "NCHW", "sortie": "logits"},
            "tuiles": {"taille_px": 200, "recouvrement_pct": 0}}
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"version": 1, "cultures": {c: conf for c in ("ble", "mais", "pommier")}}), encoding="utf-8")
    clf = ClassifieurTuiles(conf, tmp_path)
    assert clf.proba_malade(Image.new("RGB", (64, 64), (155, 107, 50))) > 0.9
    assert clf.proba_malade(Image.new("RGB", (64, 64), (75, 140, 45))) < 0.1
    bilan = executer(options(demo, registre=reg))
    assert bilan.nb_images == 104 and bilan.nb_malades > 0
    page = (bilan.dossier_resultats / "rapport.html").read_text(encoding="utf-8")
    assert "Modèle factice" not in page


def test_tuiles_couvrent_l_image():
    t = _tuiles(4000, 3000, 1000, 0.25)
    assert t[0] == (0, 0, 1000, 1000) and t[-1] == (3000, 2000, 4000, 3000)
    assert _tuiles(800, 600, None, 0) == [(0, 0, 800, 600)]


def test_nms_garde_la_meilleure():
    b = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [50, 50, 60, 60]], np.float32)
    assert sorted(nms(b, np.array([0.9, 0.8, 0.7]), 0.45)) == [0, 2]


def test_decodage_yolov8_letterbox():
    # image 1280 × 960 -> letterbox 640 : échelle 0,5, bandes de 80 px en haut et en bas
    sortie = np.zeros((1, 4 + 2, 3), np.float32)
    sortie[0, :4, 0] = [320, 320, 100, 50]; sortie[0, 4:, 0] = [0.1, 0.9]   # malade 0,9
    sortie[0, :4, 1] = [322, 321, 100, 50]; sortie[0, 4:, 1] = [0.1, 0.6]   # doublon -> NMS
    sortie[0, :4, 2] = [100, 200, 20, 20];  sortie[0, 4:, 2] = [0.02, 0.01]  # sous le seuil min
    res = decoder_yolov8(sortie, 0.5, (0, 80), (1280, 960), 0.05, 0.45, nb_classes=2)
    assert len(res) == 1
    c, s, (x1, y1, x2, y2) = res[0]
    assert c == 1 and s == pytest.approx(0.9)
    assert (x1, y1, x2, y2) == pytest.approx((540, 430, 740, 530))


class _Extracteur:
    seuil = 0.25
    def boites(self, image):
        return [("feuille", 0.9, (0, 0, 50, 50)), ("feuille", 0.8, (60, 0, 110, 50)), ("feuille", 0.1, (0, 60, 50, 110))]


class _Classifieur:
    def proba_malade(self, image):
        return float(np.asarray(image)[..., 0].mean() / 255)


def test_deux_etages_classe_chaque_feuille():
    im = np.zeros((120, 120, 3), np.uint8); im[:, 60:, 0] = 255   # feuille de droite « rouge »
    r: ResultatImage = DeuxEtages(_Extracteur(), _Classifieur(), 0.5).analyser(Image.fromarray(im))
    assert r.nb_elements == 2 and r.malade and len(r.detections) == 1
    assert r.detections[0].boite == (60, 0, 110, 50)


def test_deux_etages_sans_feuille():
    class Vide(_Extracteur):
        def boites(self, image):
            return []
    r = DeuxEtages(Vide(), _Classifieur(), 0.5).analyser(Image.new("RGB", (50, 50)))
    assert not r.malade and r.remarque == "aucune feuille extraite"


def test_letterbox_comme_a_l_entrainement():
    from analyse.modeles import letterbox_image
    feuille = Image.new("RGB", (200, 100), (0, 200, 0))      # feuille allongée
    lb = np.asarray(letterbox_image(feuille, 64, 64))
    assert lb.shape == (64, 64, 3)
    assert (lb[0, 32] == 114).all() and (lb[-1, 32] == 114).all()   # bandes grises en haut et en bas
    assert lb[32, 0, 1] == 200 and lb[32, 63, 1] == 200             # pleine largeur : pas de déformation


def test_registre_redimensionnement_inconnu(tmp_path):
    _modele_rouge_vert(tmp_path / "rv.onnx")
    conf = {"onnx": "rv.onnx", "classes": ["SAIN", "MALADE"], "classe_malade": "MALADE",
            "entree": {"largeur": 64, "hauteur": 64, "redimensionnement": "carre"}}
    with pytest.raises(ValueError, match="redimensionnement"):
        ClassifieurTuiles(conf, tmp_path)
    conf["entree"].update(redimensionnement="letterbox", normalisation="aucune", jpeg_qualite=75)
    clf = ClassifieurTuiles(conf, tmp_path)
    assert clf.proba_malade(Image.new("RGB", (120, 40), (155, 107, 50))) > 0.5
