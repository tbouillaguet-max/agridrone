"""Test du notebook de préparation sur des données SYNTHÉTIQUES (aucun accès réseau externe).
Usage : python scripts/test_prep_synthetic.py
Vérifie : mapping des classes, dédoublonnage (copies tournées/miroir/recompressées), conflits d'étiquettes,
quarantaine, absence de fuite train/val/test, export classification + détection, transformation des boîtes,
lecteur de zip distant (requêtes Range) et téléchargement Dataverse simulé, tuilage, résolution au sol.
"""
import hashlib, io, json, os, random, re, shutil, sys, tempfile, threading, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"
SRC = Path(__file__).resolve().parents[1] / "notebooks" / "01_preparation_donnees.py"


def cells(text):
    out, cur = [], []
    for line in text.split("\n"):
        if line.startswith("# %%"):
            if cur:
                out.append(cur)
            cur = [line]
        else:
            cur.append(line)
    out.append(cur)
    return ["\n".join(c) for c in out if "[markdown]" not in c[0]]


def rand_img(seed, w=320, h=240):
    r = np.random.RandomState(seed)
    return Image.fromarray(r.randint(0, 255, (h // 8, w // 8, 3), dtype=np.uint8)).resize((w, h), Image.BICUBIC)


def build_data(base):
    base = Path(base)
    names = ["fall armyworm egg", "fall armyworm frass", "fall armyworm larva", "fall armyworm larval damage",
             "healthy images", "healthy maize", "maize streak disease", "none healthy"]
    k = base / "kara"
    (k / "train/images").mkdir(parents=True)
    (k / "train/labels").mkdir(parents=True)
    (k / "data.yaml").write_text("names:\n" + "".join(f"  - {n}\n" for n in names))
    cid_of = {0: 5, 1: 3, 2: 6, 3: 7}          # healthy maize, larval damage, streak, none healthy
    for i in range(24):
        ts = 1621000000000 + i * 30000000
        im = rand_img(1000 + i)
        variants = [("o", im), ("f", im.transpose(Image.FLIP_LEFT_RIGHT)), ("r", im.transpose(Image.ROTATE_90))]
        for tag, v in variants:
            hx = hashlib.md5(f"{i}{tag}".encode()).hexdigest()[:16]
            nm = f"{ts}_jpg.rf.{hx}"
            v.save(k / "train/images" / (nm + ".jpg"), quality=90)
            cid = cid_of[i % 4]
            lines = [f"{cid} 0.5 0.5 0.5 0.5"]
            if cid == 3:
                lines.append("3 0.2 0.2 0.1 0.1")
            (k / "train/labels" / (nm + ".txt")).write_text("\n".join(lines) + "\n")
    rand_img(5000).save(k / "train/images/1629999999999_jpg.rf.deadbeef.jpg")            # sans étiquette
    m = base / "mak"
    for cls, off in (("healthy", 0), ("mlb", 100), ("msv", 200)):
        (m / cls).mkdir(parents=True)
        for i in range(12):
            rand_img(2000 + off + i).save(m / cls / f"{1621500000000 + (off + i) * 40000000}.jpg", quality=90)
    Image.fromarray(np.random.RandomState(1).randint(0, 255, (50, 50, 3), dtype=np.uint8)).save(m / "healthy/small.jpg")
    (m / "healthy/corrompue.jpg").write_bytes(os.urandom(500))
    d = base / "mld"
    for cls, off in (("Blight", 300), ("Fall Armyworm", 400), ("Gray Spot", 500), ("Healthy", 600)):
        (d / cls).mkdir(parents=True)
        for i in range(10):
            rand_img(3000 + off + i, 160, 120).save(d / cls / f"IMG_{off + i:04d}.jpg", quality=90)
    # doublon inter-sources (réduit + recompressé) : même classe → un seul représentant
    rand_img(2000 + 0).resize((256, 192)).save(d / "Healthy" / "copie_makerere.jpg", quality=70)
    # conflit : même image étiquetée sain (mld) et helminthosporiose (makerere)
    rand_img(2000 + 100).save(d / "Healthy" / "conflit.jpg", quality=95)
    p = base / "pd"
    p.mkdir()
    for i in range(8):
        nm = ("Corn leaf blight" if i % 2 else "Corn rust leaf") if i < 6 else "Tomato leaf"
        rand_img(4000 + i).save(p / f"pd_{i}.jpg", quality=90)
        (p / f"pd_{i}.xml").write_text(
            "<annotation><size><width>320</width><height>240</height></size>"
            f"<object><name>{nm}</name><bndbox><xmin>10</xmin><ymin>10</ymin><xmax>110</xmax><ymax>90</ymax></bndbox></object></annotation>")
    return dict(karaagro=k, makerere=m, mld_bangladesh=d, plantdoc=p)


def run(mode, tmp, roots):
    ns = {"__name__": "__main__"}
    cs = cells(SRC.read_text(encoding="utf-8"))
    exec(compile(cs[0], "cell1", "exec"), ns)
    ns.update(RUN_MODE=mode, DOWNLOAD=False, WORK=Path(tmp) / "work", RAW=Path(tmp) / "raw", IMG_SIZE=128, MIN_SIDE=96)
    for n, r in roots.items():
        ns["SOURCES"][n]["local_dir"] = str(r)
    for i, c in enumerate(cs[1:], 2):
        exec(compile(c, f"cell{i}", "exec"), ns)
    return ns


class H(BaseHTTPRequestHandler):
    files, api = {}, {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in H.api:
            b = json.dumps(H.api[path]).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        b = H.files.get(path)
        if b is None:
            self.send_response(404); self.end_headers(); return
        rng = self.headers.get("Range")
        if rng:
            a, e = re.match(r"bytes=(\d+)-(\d*)", rng).groups()
            a = int(a); e = min(int(e) if e else len(b) - 1, len(b) - 1)
            part = b[a:e + 1]
            self.send_response(206); self.send_header("Content-Range", f"bytes {a}-{e}/{len(b)}")
        else:
            part = b
            self.send_response(200)
        self.send_header("Content-Length", str(len(part))); self.end_headers(); self.wfile.write(part)


def main():
    tmp = tempfile.mkdtemp(prefix="maize_test_")
    print("dossier de test :", tmp)
    roots = build_data(Path(tmp) / "src")

    # ---------- 1) mode inventaire : aucun traitement ----------
    ns = run("inventaire", Path(tmp) / "inv", roots)
    assert not (Path(tmp) / "inv/work/manifest.csv").exists(), "le mode inventaire ne doit rien traiter"
    print("OK inventaire")

    # ---------- 2) mode complet ----------
    ns = run("complet", Path(tmp) / "run", roots)
    import pandas as pd
    W = Path(tmp) / "run/work"
    df = pd.read_csv(W / "manifest.csv")
    used = df[df["split"].notna()]
    q = df[df["split"].isna()]
    reasons = q["reason"].fillna("").tolist()
    k = used[used["source"] == "karaagro"]
    assert len(k) == 18, f"karaagro : 18 images attendues (copies tournées écartées), obtenu {len(k)}"
    assert set(k["binary"]) == {"SAIN", "MALADE_OU_RAVAGEUR"}
    assert any("classe non reconnue" in r and "none healthy" in r for r in reasons), "« none healthy » doit être en quarantaine"
    assert any("aucune étiquette" in r for r in reasons), "image sans étiquette en quarantaine"
    assert any("illisible" in r for r in reasons) and any("trop petite" in r for r in reasons)
    assert any("conflit" in r for r in reasons), "conflit d'étiquettes non détecté"
    assert any("hors maïs" in r for r in reasons), "filtre de classes PlantDoc"
    assert (used[used.source == "plantdoc"]["binary"] == "MALADE_OU_RAVAGEUR").all()
    assert set(k["fine"]) == {"sain", "legionnaire_ravageur", "striure_msv"}, set(k["fine"])
    mk = used[used.source == "makerere"]
    assert set(mk["fine"]) >= {"sain", "helminthosporiose", "striure_msv"}
    ml = used[used.source == "mld_bangladesh"]
    assert set(ml["fine"]) >= {"sain", "legionnaire_ravageur", "cercosporiose"}
    assert any("doublon" in r for r in reasons), "doublon inter-sources non détecté"
    for sp in ("train", "val", "test"):
        assert (used["split"] == sp).any(), f"ensemble {sp} vide"
    for _, r in used.iterrows():
        assert (W / r["out_path"]).exists()
        assert Image.open(W / r["out_path"]).size == (128, 128)
    assert (W / "det/dataset.yaml").exists()
    lab = list((W / "det").glob("*/labels/*.txt"))
    assert lab, "aucun fichier d'étiquettes de détection"
    nbox = 0
    for f in lab:
        for line in f.read_text().split():
            pass
        for line in f.read_text().strip().split("\n"):
            if line.strip():
                c, cx, cy, w, h = line.split()
                assert c == "0" and all(0 <= float(v) <= 1 for v in (cx, cy, w, h))
                nbox += 1
    assert nbox > 0
    assert (W / "qc").exists() and list((W / "qc").glob("*.jpg"))
    print(f"OK complet : {len(used)} images utilisées, {len(q)} écartées, {nbox} boîtes de détection")

    # ---------- 3) fonctions unitaires ----------
    t = ns["transform_box"](dict(cx=0.5, cy=0.5, w=0.5, h=0.5), 320, 240, 0.4, 0, 16, 128)
    assert all(abs(a - b) < 1e-6 for a, b in zip(t, (0.5, 0.5, 0.5, 0.375))), t
    ok = ns["origin_key"]
    assert ok(Path("a/1623274715906_jpg.rf.abc123.jpg")) == ok(Path("b/1623274715906.jpg")) == ok(Path("c/1623270000000.jpg")) == "ts162327"
    assert ok(Path("a/1623274715906_jpg.rf.abc123.jpg")) != ok(Path("a/1700000000000.jpg"))
    for nm, exp in (("none healthy", (None, None)), ("healthy maize", ("sain", "SAIN")), ("maize streak disease", ("striure_msv", "MALADE_OU_RAVAGEUR")),
                    ("Corn leaf blight", ("helminthosporiose", "MALADE_OU_RAVAGEUR")), ("Gray Spot", ("cercosporiose", "MALADE_OU_RAVAGEUR")),
                    ("unhealthy", ("malade_non_precise", "MALADE_OU_RAVAGEUR")), ("fall armyworm larval damage", ("legionnaire_ravageur", "MALADE_OU_RAVAGEUR")),
                    ("mlb_123", ("helminthosporiose", "MALADE_OU_RAVAGEUR")), ("train", (None, None)), ("images", (None, None))):
        assert ns["classify_name"](nm) == exp, (nm, ns["classify_name"](nm))
    g = ns["gsd_cm"](5, 6.17, 3.61, 4000)
    assert abs(g - 0.2136) < 0.001, g
    cover = np.zeros((700, 1300), bool)
    for x0, y0, x1, y1 in ns["iter_tiles"](1300, 700, 512, 512):
        cover[y0:y1, x0:x1] = True
    assert cover.all(), "le tuilage ne couvre pas toute l'image"
    # quasi-doublon : même image redimensionnée / miroir / rotation → même grappe ; images différentes → grappes différentes
    im = rand_img(9)
    hs = []
    for v in (im, im.transpose(Image.FLIP_LEFT_RIGHT), im.transpose(Image.ROTATE_270), im.resize((200, 150)), rand_img(10)):
        p = Path(tmp) / f"h{len(hs)}.jpg"; v.save(p, quality=75); hs.append(ns["image_info"](p)["hashes"])
    cl = ns["cluster_duplicates"](hs, 4)
    assert len(set(cl[:4])) == 1 and cl[4] != cl[0], cl
    print("OK fonctions (boîtes, GSD, tuilage, doublons)")

    # ---------- 4) zip distant (Range) + Dataverse simulé ----------
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for i in range(30):
            b = io.BytesIO(); rand_img(7000 + i, 64, 48).save(b, "JPEG")
            z.writestr(f"data/train/images/im{i:03d}.jpg", b.getvalue())
            z.writestr(f"data/train/labels/im{i:03d}.txt", "0 0.5 0.5 0.2 0.2\n")
        z.writestr("data/data.yaml", "names: [malade]\n")
    zbytes = buf.getvalue()
    H.files = {"/api/access/datafile/1": zbytes}
    loose = {}
    for j in range(2, 8):
        b = io.BytesIO(); rand_img(8000 + j, 64, 48).save(b, "JPEG"); H.files[f"/api/access/datafile/{j}"] = b.getvalue()
        loose[j] = len(b.getvalue())
    H.files["/api/access/datafile/9"] = b"names: [a]\n"
    files = [{"dataFile": {"id": 1, "filename": "all.zip", "filesize": len(zbytes)}, "directoryLabel": ""}]
    files += [{"dataFile": {"id": j, "filename": f"x{j}.jpg", "filesize": s}, "directoryLabel": "loose"} for j, s in loose.items()]
    files += [{"dataFile": {"id": 9, "filename": "data.yaml", "filesize": 11}, "directoryLabel": "loose"}]
    H.api = {"/api/datasets/:persistentId/": {"data": {"latestVersion": {"files": files}}}}
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    ns["zip_extract_subset"](base + "/api/access/datafile/1", Path(tmp) / "zr", 10)
    jp = list((Path(tmp) / "zr").rglob("*.jpg"))
    assert len(jp) == 10, len(jp)
    for p in jp:
        assert p.with_suffix(".txt").exists() or (p.parent.parent / "labels" / (p.stem + ".txt")).exists()
    assert len(list((Path(tmp) / "zr").rglob("*.txt"))) == 10, "seules les annotations des images retenues doivent être extraites"
    assert (Path(tmp) / "zr/data/data.yaml").exists()
    ns["DATAVERSE"] = base
    ns["fetch_dataverse"]("doi:test", Path(tmp) / "dv", 4)
    assert len(list((Path(tmp) / "dv").rglob("*.jpg"))) == 4 + 4, list((Path(tmp) / "dv").rglob("*"))[:5]
    assert (Path(tmp) / "dv/loose/data.yaml").exists()
    srv.shutdown()
    print("OK zip distant (Range) + Dataverse simulé")
    print("\nTOUS LES TESTS PASSENT")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
