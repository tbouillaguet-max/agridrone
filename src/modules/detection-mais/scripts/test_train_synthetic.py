"""Tests hors ligne du notebook 02 (entraînement / comparaison) sur un faux jeu de données.

Usage : python scripts/test_train_synthetic.py
- fabrique un faux maize_prep/ (cls/, det/, manifest.csv) : feuilles vertes, taches brunes = malade ;
- exécute le notebook en mode test_rapide puis en mode complet (2 époques), sans poids pré-entraînés ;
- vérifie les fichiers produits, la reprise (modèles terminés sautés) et les fonctions de métriques.
Prévu pour un CPU : petites images (128 px), peu d'images.
"""
import json, math, os, random, re, shutil, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "02_entrainement_comparaison.py"
TMP = Path(os.environ.get("TEST_TMP", "/tmp/test_train_02"))
IMG = 128


def leaf(rng, sick):
    im = Image.new("RGB", (IMG, IMG), (60 + rng.randint(-15, 15), 130 + rng.randint(-20, 20), 50))
    d = ImageDraw.Draw(im)
    for k in range(6):                                    # nervures
        x = rng.randint(0, IMG)
        d.line([(x, 0), (x + rng.randint(-30, 30), IMG)], fill=(90, 170, 70), width=2)
    boxes = []
    if sick:
        for _ in range(rng.randint(1, 4)):                # lésions brunes
            w, h = rng.randint(10, 30), rng.randint(6, 18)
            x, y = rng.randint(0, IMG - w), rng.randint(0, IMG - h)
            d.ellipse([x, y, x + w, y + h], fill=(140 + rng.randint(-20, 20), 90, 40))
            boxes.append(((x + w / 2) / IMG, (y + h / 2) / IMG, w / IMG, h / IMG))
    return im.filter(ImageFilter.GaussianBlur(0.6)), boxes


def make_data(n_per=30):
    rng = random.Random(0)
    base = TMP / "maize_prep"
    shutil.rmtree(TMP, ignore_errors=True)
    rows = []
    for sp, n in (("train", n_per), ("val", n_per // 2), ("test", n_per // 2)):
        for cl in ("SAIN", "MALADE_OU_RAVAGEUR"):
            for i in range(n):
                src = "srcA" if i % 2 else "srcB"
                im, boxes = leaf(rng, cl != "SAIN")
                name = f"{src}__img{sp}{cl[0]}{i}__{i:08x}.jpg"
                rel = f"cls/{sp}/{cl}/{name}"
                (base / rel).parent.mkdir(parents=True, exist_ok=True)
                im.save(base / rel, quality=92)
                if src == "srcA":                         # seule la source A a des boîtes
                    di, dl = base / "det" / sp / "images", base / "det" / sp / "labels"
                    di.mkdir(parents=True, exist_ok=True); dl.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(base / rel, di / name)
                    (dl / (Path(name).stem + ".txt")).write_text(
                        "".join(f"0 {a:.6f} {b:.6f} {c:.6f} {e:.6f}\n" for a, b, c, e in boxes))
                fine = "sain" if cl == "SAIN" else ("rouille_commune" if i % 3 else "helminthosporiose")
                rows.append(dict(source=src, out_path=rel, fine=fine, group=f"{sp}-{src}-{i // 3}",
                                 domain="champ", split=sp, binary=cl))
    import pandas as pd
    pd.DataFrame(rows).to_csv(base / "manifest.csv", index=False)
    (base / "det" / "dataset.yaml").write_text(
        "path: /kaggle/working/maize_prep/det\ntrain: train/images\nval: val/images\ntest: test/images\n"
        "names:\n  0: malade_ou_ravageur\n")
    return base


def run_notebook(mode, out, extra_models=""):
    """Exécute la source du notebook avec des paramètres de test (mêmes cellules, valeurs remplacées)."""
    src = NB.read_text(encoding="utf-8")
    subs = {
        r'^MODE = "test_rapide"': f'MODE = "{mode}"',
        r"^IMG_SIZE = 512": f"IMG_SIZE = {IMG}",
        r"^PRETRAINED = True": "PRETRAINED = False",
        r"^DATA_DIR = None": f'DATA_DIR = "{TMP / "maize_prep"}"',
        r'^OUT = Path\("/kaggle/working/train"\) if ON_KAGGLE else Path\("./train_out"\)': f'OUT = Path("{out}")',
    }
    for a, b in subs.items():
        src, n = re.subn(a, b, src, flags=re.M)
        assert n == 1, f"motif introuvable : {a}"
    src = src.replace("RESULTS, PER = run_all()", extra_models + "\nRESULTS, PER = run_all()")
    g = {"__name__": "__main__"}
    t = time.time()
    exec(compile(src, str(NB), "exec"), g)
    print(f"--- mode {mode} : {time.time() - t:.0f} s")
    return g


def check_outputs(out, names):
    res = Path(out) / "resultats"
    for f in ("comparaison.csv", "comparaison.md", "pr_test.png", "choix_modele.json",
              "detail_par_source_et_maladie.csv"):
        assert (res / f).exists(), f"manquant : {f}"
    import pandas as pd
    c = pd.read_csv(res / "comparaison.csv")
    assert set(names) <= set(c["modele"]), (set(names), set(c["modele"]))
    for n in names:
        assert (Path(out) / "export" / f"{n}.pt").exists(), n
        assert (res / "preds" / f"{n}_test.csv").exists(), n
    # seuil choisi sur la validation : le rappel validation atteint la cible
    assert (c["val_rappel"] >= 0.95 - 1e-9).all(), c[["modele", "val_rappel"]]
    ch = json.loads((res / "choix_modele.json").read_text())
    assert ch["modele"] in names
    return c


def unit_tests(g):
    ct, mt = g["choose_threshold"], g["metrics_at"]
    y = np.array([0, 0, 1, 1, 1, 1]); s = np.array([0.1, 0.6, 0.4, 0.7, 0.8, 0.9])
    t = ct(y, s, 0.75)
    assert t == 0.7, t                               # 3/4 positifs au-dessus de 0.7
    m = mt(y, s, t)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (3, 0, 1, 2), m
    assert ct(y, s, 1.0) == 0.4
    assert abs(mt(y, s, 0.4)["precision"] - 0.8) < 1e-9
    import pandas as pd
    df = pd.DataFrame(dict(y=y, score=s, group=["a", "a", "b", "b", "c", "c"]))
    (r, p) = g["group_bootstrap"](df, 0.7, n=50)
    assert 0 <= r[0] <= r[1] <= 1
    print("tests unitaires des métriques : OK")


if __name__ == "__main__":
    make_data()
    out = TMP / "train_out"
    # 1) test rapide : tous les modèles activés par défaut (RT-DETR exclu, trop lourd)
    g = run_notebook("test_rapide", out)
    unit_tests(g)
    default = [k for k, v in g["MODELS"].items() if v["enabled"]]
    c = check_outputs(out, default)
    print(c[["modele", "val_AP", "test_rappel", "test_precision", "cpu_ms_img"]].to_string())
    # 2) mode complet, 2 époques, puis relance : les modèles terminés doivent être sautés
    out2 = TMP / "train_full"
    small = ("for _k, _v in MODELS.items():\n"
             "    _v.update(epochs=2, batch=16)\n"
             "MODELS['dinov2s_lin']['img'] = 112\n")
    g = run_notebook("complet", out2, small)
    c = check_outputs(out2, default)
    hist = (out2 / "runs" / "effnet_b0" / "historique.csv").read_text().strip().splitlines()
    assert len(hist) == 3, hist                       # en-tête + 2 époques
    done = json.loads((out2 / "resultats" / "modeles_termines.json").read_text())
    assert set(done) == set(default), set(done)
    t = time.time()
    g = run_notebook("complet", out2, small)
    assert time.time() - t < 120, "la relance aurait dû sauter les modèles terminés"
    check_outputs(out2, default)
    # 3) reprise d'un classifieur interrompu : on retire 'effnet_b0' des terminés et on passe à 3 époques
    done.pop("effnet_b0")
    (out2 / "resultats" / "modeles_termines.json").write_text(json.dumps(done))
    g = run_notebook("complet", out2, small + "MODELS['effnet_b0']['epochs'] = 3\n")
    hist = (out2 / "runs" / "effnet_b0" / "historique.csv").read_text().strip().splitlines()
    assert len(hist) == 4, hist                       # reprise à l'époque 2 → 3 époques au total
    print("\nTOUS LES TESTS PASSENT")
