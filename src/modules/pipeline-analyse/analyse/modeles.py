"""Étapes 3 et 4 — registre des modèles et inférence (contrat générique).

Contrat d'un modèle (validé avec Tom) : fichier ONNX exécuté sur CPU ;
entrée = une image (ou une tuile, ou une feuille) ; sortie = sain/malade + score,
et des boîtes pour les détecteurs.

Chaque modèle expose ``analyser(image PIL RGB) -> ResultatImage``.
Une image est « malade » si au moins un élément (tuile, boîte, feuille) atteint le
seuil ; son score est celui de l'élément le plus sûr.
"""
from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import contrat as C
from .contrat import erreur


# ----------------------------------------------------------------------------- résultats
@dataclass
class Detection:
    classe: str
    score: float
    boite: tuple[float, float, float, float] | None  # x1, y1, x2, y2 en pixels de l'image d'origine


@dataclass
class ResultatImage:
    score: float                 # probabilité « malade » de l'élément le plus sûr (0 si aucun élément)
    malade: bool
    detections: list[Detection] = field(default_factory=list)  # éléments au-dessus du seuil
    nb_elements: int = 0         # tuiles, boîtes candidates ou feuilles examinées
    remarque: str = ""


# ----------------------------------------------------------------------------- outils
MOYENNE_IMAGENET = (0.485, 0.456, 0.406)
ECART_IMAGENET = (0.229, 0.224, 0.225)


REDIMENSIONNEMENTS = ("etirer", "letterbox")


def letterbox_image(image: Image.Image, largeur: int, hauteur: int, gris: int = 114) -> Image.Image:
    """Redimensionne sans déformer (côté long ajusté) et centre sur un fond gris, comme à l'entraînement."""
    r = min(largeur / image.width, hauteur / image.height)
    nw, nh = max(1, round(image.width * r)), max(1, round(image.height * r))
    fond = Image.new("RGB", (largeur, hauteur), (gris, gris, gris))
    fond.paste(image.resize((nw, nh), Image.BILINEAR), ((largeur - nw) // 2, (hauteur - nh) // 2))
    return fond


def _recompresser(image: Image.Image, qualite: int) -> Image.Image:
    tampon = io.BytesIO()
    image.save(tampon, "JPEG", quality=qualite)
    tampon.seek(0)
    return Image.open(tampon).convert("RGB")


def _preparer(image: Image.Image, largeur: int, hauteur: int, normalisation: str, disposition: str,
              redimensionnement: str = "etirer", gris: int = 114) -> np.ndarray:
    if redimensionnement == "letterbox":
        image = letterbox_image(image, largeur, hauteur, gris)
    else:
        image = image.resize((largeur, hauteur), Image.BILINEAR)
    x = np.asarray(image, dtype=np.float32) / 255.0
    if normalisation == "imagenet":
        x = (x - np.array(MOYENNE_IMAGENET, np.float32)) / np.array(ECART_IMAGENET, np.float32)
    if disposition == "NCHW":
        x = x.transpose(2, 0, 1)
    return x[None, ...]


def _softmax(v: np.ndarray) -> np.ndarray:
    v = v - v.max()
    e = np.exp(v)
    return e / e.sum()


def _tuiles(largeur: int, hauteur: int, taille: int | None, recouvrement: float) -> list[tuple[int, int, int, int]]:
    """Découpe régulière ; la dernière tuile de chaque rangée est recalée sur le bord."""
    if not taille or taille >= max(largeur, hauteur):
        return [(0, 0, largeur, hauteur)]
    pas = max(1, int(taille * (1 - recouvrement)))
    def positions(n: int) -> list[int]:
        if n <= taille:
            return [0]
        p = list(range(0, n - taille + 1, pas))
        if p[-1] != n - taille:
            p.append(n - taille)
        return p
    return [(x, y, min(x + taille, largeur), min(y + taille, hauteur))
            for y in positions(hauteur) for x in positions(largeur)]


def nms(boites: np.ndarray, scores: np.ndarray, seuil_iou: float) -> list[int]:
    """Suppression des non-maxima (boîtes x1, y1, x2, y2)."""
    ordre = scores.argsort()[::-1]
    gardees: list[int] = []
    while ordre.size:
        i = int(ordre[0])
        gardees.append(i)
        if ordre.size == 1:
            break
        r = ordre[1:]
        xx1 = np.maximum(boites[i, 0], boites[r, 0]); yy1 = np.maximum(boites[i, 1], boites[r, 1])
        xx2 = np.minimum(boites[i, 2], boites[r, 2]); yy2 = np.minimum(boites[i, 3], boites[r, 3])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        aire = lambda b: (b[..., 2] - b[..., 0]) * (b[..., 3] - b[..., 1])
        iou = inter / (aire(boites[i]) + aire(boites[r]) - inter + 1e-9)
        ordre = r[iou <= seuil_iou]
    return gardees


def decoder_yolov8(sortie: np.ndarray, echelle: float, decalage: tuple[float, float],
                   taille_origine: tuple[int, int], seuil_min: float, seuil_iou: float,
                   nb_classes: int | None = None
                   ) -> list[tuple[int, float, tuple[float, float, float, float]]]:
    """Sortie d'un export ONNX Ultralytics YOLOv8/v11 : [1, 4 + nb_classes, N] (cx, cy, w, h en pixels
    de l'entrée letterbox). Renvoie [(indice_classe, score, (x1, y1, x2, y2) image d'origine)]."""
    s = sortie[0]
    lignes = 4 + nb_classes if nb_classes else None
    if (lignes and s.shape[0] != lignes and s.shape[1] == lignes) or (not lignes and s.shape[0] > s.shape[1]):
        s = s.T  # certains exports sont transposés [N, 4 + nc]
    if lignes and s.shape[0] != lignes:
        raise ValueError(f"sortie du détecteur de forme {sortie.shape} : {lignes} lignes attendues "
                         f"(4 + {nb_classes} classes du registre)")
    boites, scores_cls = s[:4].T, s[4:].T
    cls = scores_cls.argmax(1)
    conf = scores_cls.max(1)
    garde = conf >= seuil_min
    boites, cls, conf = boites[garde], cls[garde], conf[garde]
    if not len(conf):
        return []
    cx, cy, w, h = boites.T
    xyxy = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
    xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - decalage[0]) / echelle
    xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - decalage[1]) / echelle
    W, H = taille_origine
    xyxy[:, [0, 2]] = xyxy[:, [0, 2]].clip(0, W); xyxy[:, [1, 3]] = xyxy[:, [1, 3]].clip(0, H)
    res = []
    for c in np.unique(cls):  # NMS par classe
        idx = np.where(cls == c)[0]
        for k in nms(xyxy[idx], conf[idx], seuil_iou):
            j = idx[k]
            res.append((int(cls[j]), float(conf[j]), tuple(float(v) for v in xyxy[j])))
    return res


def _letterbox(image: Image.Image, taille: int) -> tuple[np.ndarray, float, tuple[float, float]]:
    W, H = image.size
    r = min(taille / W, taille / H)
    nw, nh = round(W * r), round(H * r)
    fond = Image.new("RGB", (taille, taille), (114, 114, 114))
    dx, dy = (taille - nw) // 2, (taille - nh) // 2
    fond.paste(image.resize((nw, nh), Image.BILINEAR), (dx, dy))
    x = np.asarray(fond, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
    return x, r, (dx, dy)


def _session(chemin: Path):
    import onnxruntime as ort
    return ort.InferenceSession(str(chemin), providers=["CPUExecutionProvider"])


# ----------------------------------------------------------------------------- modèles
class ClassifieurTuiles:
    """Classification (ONNX) d'une image entière ou de tuiles. Score = proba de la classe malade."""

    def __init__(self, conf: dict, base: Path, session=None):
        self.classes: list[str] = conf["classes"]
        self.classe_malade: str = conf.get("classe_malade", "malade")
        self.seuil: float = float(conf.get("seuil", 0.5))
        e = conf.get("entree", {})
        self.largeur, self.hauteur = int(e.get("largeur", 224)), int(e.get("hauteur", 224))
        self.normalisation = e.get("normalisation", "imagenet")
        self.disposition = e.get("disposition", "NCHW")
        self.sortie = e.get("sortie", "logits")
        self.redimensionnement = e.get("redimensionnement", "etirer")
        self.gris = int(e.get("couleur_bandes", 114))
        self.jpeg = e.get("jpeg_qualite")  # recompression JPEG avant préparation (imite l'harmonisation du dataset)
        if self.redimensionnement not in REDIMENSIONNEMENTS:
            raise ValueError(f"entree.redimensionnement « {self.redimensionnement} » inconnu "
                             f"(attendu : {', '.join(REDIMENSIONNEMENTS)})")
        if self.jpeg is not None and not (isinstance(self.jpeg, int) and 1 <= self.jpeg <= 100):
            raise ValueError(f"entree.jpeg_qualite {self.jpeg!r} : entier de 1 à 100 attendu")
        if self.normalisation not in ("imagenet", "aucune") or self.disposition not in ("NCHW", "NHWC") \
                or self.sortie not in ("logits", "probas"):
            raise ValueError("entree : normalisation imagenet|aucune, disposition NCHW|NHWC, sortie logits|probas")
        t = conf.get("tuiles") or {}
        self.taille_tuile = t.get("taille_px")
        self.recouvrement = float(t.get("recouvrement_pct", 0)) / 100
        self.session = session or _session(base / conf["onnx"])
        self.nom_entree = self.session.get_inputs()[0].name
        self.i_malade = self.classes.index(self.classe_malade)

    def proba_malade(self, image: Image.Image) -> float:
        if self.jpeg:
            image = _recompresser(image, self.jpeg)
        x = _preparer(image, self.largeur, self.hauteur, self.normalisation, self.disposition,
                      self.redimensionnement, self.gris)
        y = np.asarray(self.session.run(None, {self.nom_entree: x})[0]).reshape(-1)
        p = _softmax(y) if self.sortie == "logits" else y
        return float(p[self.i_malade])

    def analyser(self, image: Image.Image) -> ResultatImage:
        W, H = image.size
        tuiles = _tuiles(W, H, self.taille_tuile, self.recouvrement)
        entiere = len(tuiles) == 1 and tuiles[0] == (0, 0, W, H)
        meilleur, dets = 0.0, []
        for (x1, y1, x2, y2) in tuiles:
            s = self.proba_malade(image.crop((x1, y1, x2, y2)))
            meilleur = max(meilleur, s)
            if s >= self.seuil:
                dets.append(Detection(self.classe_malade, s, None if entiere else (x1, y1, x2, y2)))
        return ResultatImage(meilleur, meilleur >= self.seuil, dets, len(tuiles))


class DetecteurYolo:
    """Détection (ONNX, export Ultralytics YOLOv8/v11). Score = confiance de la meilleure boîte malade."""

    def __init__(self, conf: dict, base: Path, session=None):
        self.classes: list[str] = conf["classes"]
        self.classes_malades = set(conf.get("classes_malades") or [c for c in self.classes if c != "sain"])
        self.seuil = float(conf.get("seuil", 0.5))
        self.taille = int(conf.get("entree", {}).get("taille", 640))
        self.seuil_iou = float(conf.get("seuil_iou", 0.45))
        self.seuil_min = float(conf.get("seuil_min", 0.05))
        self.session = session or _session(base / conf["onnx"])
        self.nom_entree = self.session.get_inputs()[0].name

    def boites(self, image: Image.Image) -> list[tuple[str, float, tuple[float, float, float, float]]]:
        x, r, d = _letterbox(image, self.taille)
        sortie = np.asarray(self.session.run(None, {self.nom_entree: x})[0])
        return [(self.classes[c], s, b) for c, s, b in
                decoder_yolov8(sortie, r, d, image.size, self.seuil_min, self.seuil_iou, len(self.classes))]

    def analyser(self, image: Image.Image) -> ResultatImage:
        bx = [b for b in self.boites(image) if b[0] in self.classes_malades]
        meilleur = max((s for _, s, _ in bx), default=0.0)
        dets = [Detection(c, s, b) for c, s, b in bx if s >= self.seuil]
        return ResultatImage(meilleur, meilleur >= self.seuil, dets, len(bx))


class DeuxEtages:
    """Pommier : 1) extraction des feuilles (détecteur), 2) classification de chaque feuille."""

    def __init__(self, extracteur, classifieur, seuil: float, classe_malade: str = "malade"):
        self.extracteur, self.classifieur = extracteur, classifieur
        self.seuil, self.classe_malade = seuil, classe_malade

    @classmethod
    def depuis_conf(cls, conf: dict, base: Path) -> "DeuxEtages":
        ext = dict(conf["extracteur"]); ext.setdefault("classes_malades", ext.get("classes", []))
        ext.setdefault("seuil", ext.get("seuil_extraction", 0.25))
        clf = dict(conf["classifieur"]); clf.setdefault("seuil", conf.get("seuil", 0.5))
        clf.pop("tuiles", None)
        return cls(DetecteurYolo(ext, base), ClassifieurTuiles(clf, base),
                   float(conf.get("seuil", 0.5)), clf.get("classe_malade", "malade"))

    def analyser(self, image: Image.Image) -> ResultatImage:
        feuilles = [b for b in self.extracteur.boites(image) if b[1] >= self.extracteur.seuil]
        meilleur, dets = 0.0, []
        for _, _, (x1, y1, x2, y2) in feuilles:
            if x2 - x1 < 4 or y2 - y1 < 4:
                continue
            s = self.classifieur.proba_malade(image.crop((int(x1), int(y1), int(x2), int(y2))))
            meilleur = max(meilleur, s)
            if s >= self.seuil:
                dets.append(Detection(self.classe_malade, s, (x1, y1, x2, y2)))
        rem = "" if feuilles else "aucune feuille extraite"
        return ResultatImage(meilleur, meilleur >= self.seuil, dets, len(feuilles), rem)


class Factice:
    """Modèle de démonstration SANS VALEUR AGRONOMIQUE : score d'une tuile = part de pixels
    « bruns » (rouge > vert). Sert à tester le pipeline tant que les vrais modèles sont en entraînement."""

    def __init__(self, conf: dict):
        self.seuil = float(conf.get("seuil", 0.5))
        self.taille_tuile = (conf.get("tuiles") or {}).get("taille_px")

    def analyser(self, image: Image.Image) -> ResultatImage:
        W, H = image.size
        a = np.asarray(image.reduce(4) if min(W, H) > 400 else image, dtype=np.int16)
        f = a.shape[1] / W
        tuiles = _tuiles(W, H, self.taille_tuile, 0)
        meilleur, dets = 0.0, []
        for (x1, y1, x2, y2) in tuiles:
            t = a[int(y1 * f):max(int(y2 * f), int(y1 * f) + 1), int(x1 * f):max(int(x2 * f), int(x1 * f) + 1)]
            brun = float(((t[..., 0] - t[..., 1]) > 15).mean())
            s = float(min(1.0, brun * 4))
            meilleur = max(meilleur, s)
            if s >= self.seuil:
                dets.append(Detection("malade", s, (x1, y1, x2, y2)))
        return ResultatImage(meilleur, meilleur >= self.seuil, dets, len(tuiles))


# ----------------------------------------------------------------------------- registre
@dataclass
class ModeleCharge:
    culture: str
    type: str
    seuil: float
    description: str
    factice: bool
    modele: object

    def analyser(self, image: Image.Image) -> ResultatImage:
        return self.modele.analyser(image)


def _fichiers_onnx(conf: dict) -> list[str]:
    t = conf.get("type")
    if t in ("classification", "detection"):
        return [conf.get("onnx")]
    if t == "deux_etages":
        return [(conf.get("extracteur") or {}).get("onnx"), (conf.get("classifieur") or {}).get("onnx")]
    return []


def charger_modele(registre: Path, culture: str) -> tuple[ModeleCharge | None, list[str], list[str]]:
    """Lit le registre, contrôle l'entrée de la culture et charge le modèle. (modèle, erreurs, avertissements)"""
    nom = registre.name
    m = C.MODULE_REGISTRE
    try:
        reg = json.loads(registre.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [erreur(str(registre), "registre des modèles introuvable", m)], []
    except (UnicodeDecodeError, ValueError) as ex:
        return None, [erreur(nom, f"JSON illisible ({ex})", m)], []
    if not isinstance(reg, dict) or reg.get("version") != C.VERSION_REGISTRE or not isinstance(reg.get("cultures"), dict):
        return None, [erreur(nom, f"format inattendu (version {C.VERSION_REGISTRE} et objet « cultures » attendus)", m)], []
    avert = []
    connues = set(reg["cultures"])
    if connues != set(C.CULTURES):
        avert.append(f"{nom} : cultures {sorted(connues)} différentes de la liste du planificateur "
                     f"{list(C.CULTURES)} (à garder identiques)")
    conf = reg["cultures"].get(culture)
    if not isinstance(conf, dict):
        return None, [erreur(nom, f"aucune entrée pour la culture « {culture} »", m)], avert
    t = conf.get("type")
    if t not in C.TYPES_MODELE:
        return None, [erreur(nom, f"{culture} : type « {t} » inconnu (attendu : {', '.join(C.TYPES_MODELE)})", m)], avert
    if t == "a_definir":
        return None, [erreur(nom, f"{culture} : aucun modèle désigné pour l'instant (type « a_definir ») ; "
                              "renseigner le modèle entraîné, ou lancer avec --modeles modeles_demo.json pour un essai", m)], avert
    base = registre.parent
    manquants = [f for f in _fichiers_onnx(conf) if not f or not (base / f).is_file()]
    if manquants:
        return None, [erreur(nom, f"{culture} : fichier ONNX introuvable : {', '.join(str(f) for f in manquants)}", m)], avert
    try:
        if t == "classification":
            modele = ClassifieurTuiles(conf, base)
        elif t == "detection":
            modele = DetecteurYolo(conf, base)
        elif t == "deux_etages":
            modele = DeuxEtages.depuis_conf(conf, base)
        else:
            modele = Factice(conf)
            avert.append(f"MODÈLE FACTICE pour « {culture} » : résultats de démonstration, sans valeur agronomique")
    except (KeyError, ValueError) as ex:
        return None, [erreur(nom, f"{culture} : configuration du modèle incomplète ({ex})", m)], avert
    except Exception as ex:  # ONNX illisible, entrée incompatible…
        return None, [erreur(nom, f"{culture} : chargement du modèle impossible ({ex.__class__.__name__}: {ex})", m)], avert
    return ModeleCharge(culture, t, float(conf.get("seuil", 0.5)), str(conf.get("description", "")),
                        t == "factice", modele), [], avert
