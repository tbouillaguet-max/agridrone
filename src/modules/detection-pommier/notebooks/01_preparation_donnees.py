# %% [markdown]
# # Notebook 01 — Préparation des données pommier (SAIN / MALADE)
#
# **But.** Construire un jeu de classification binaire SAIN / MALADE propre et **sans raccourci de source** :
# - **AppleLeaf9** (GitHub, CC BY 4.0) : 14 582 feuilles, 9 dossiers (`Health` = SAIN, les 8 autres = MALADE) ;
# - **Plant Pathology 2021 – FGVC8** (compétition Kaggle) : on ne prend **que les feuilles saines** (`healthy`),
#   prises dans le même verger et avec le même appareil que la plupart des feuilles malades d'AppleLeaf9 ;
# - **PlantDoc** (pommier, CC BY 4.0) : **test externe** uniquement (images web, autre domaine) ;
# - **GYMNSA** (Mendeley, CC BY 4.0) : tuiles de **drone** de verger de poiriers (rouille), gardées à part
#   pour l'adaptation au point de vue drone. Elles ne sont jamais mélangées au jeu feuille.
#
# **Pourquoi « harmoniser ».** Dans AppleLeaf9, les 516 feuilles saines viennent toutes de FGVC2020 (2048×1365),
# alors que les malades viennent surtout de FGVC2021 réduites (958×640) et d'ATLDSD (512×512). Sans précaution,
# le modèle apprend « grande image = saine ». On ramène donc toutes les images du jeu principal au même traitement :
# côté long 958 px, puis JPEG qualité 75 (celle utilisée par les auteurs d'AppleLeaf9), puis format carré `IMG_SIZE`.
# Même problème dans GYMNSA : les tuiles sans symptôme sont en JPEG ~100, les tuiles malades en JPEG 75. Elles passent
# donc aussi par la même compression.
#
# **Réglages Kaggle (panneau de droite).**
# - *Add Input* → compétition **plant-pathology-2021-fgvc8** (accepter le règlement une fois sur Kaggle).
# - Accelerator = *None* (le CPU suffit). Internet = *On* (téléchargement d'AppleLeaf9, PlantDoc et GYMNSA).
#
# **Deux passes.**
# 1. `RUN_MODE = "inventaire"` : vérifie que tout est trouvé et décrit les sources (rien n'est exporté).
# 2. `RUN_MODE = "complet"` : prépare et exporte tout, puis affiche les contrôles (effectifs, raccourcis, fuites).
#
# **Sorties** (dans `/kaggle/working/apple_prep`, puis *Save Version* pour les réutiliser dans le notebook 02) :
# `cls/{train,val,test,test_externe}/{SAIN,MALADE}/`, `drone/`, `manifest.csv`, `classes.json`,
# `effectifs.csv`, `quarantaine.csv`, `qc/`, `README_dataset.md`.

# %%
# ===== 1. PARAMÈTRES (c'est la seule cellule à modifier) =====
from pathlib import Path

RUN_MODE = "inventaire"         # "inventaire" (décrire) ou "complet" (préparer et exporter)
DOWNLOAD = True                 # False : n'utilise que les dossiers locaux / inputs Kaggle (aucun réseau)
SEED = 42
IMG_SIZE = 512                  # côté des images exportées (carré, bandes grises si besoin)
HARMONIZE_LONG_SIDE = 958       # côté long des images FGVC2021 telles que réduites dans AppleLeaf9
HARMONIZE_QUALITY = None        # qualité JPEG d'harmonisation ; None = estimée sur AppleLeaf9 (attendu : 75)
MIN_SIDE = 96                   # images dont un côté est plus petit : rejetées
DUP_HAMMING = 4                 # distance de hachage (sur 64 bits) en dessous de laquelle deux images sont des doublons
SPLIT = (0.70, 0.15, 0.15)      # train / val / test du jeu principal
FGVC8_MAX_SAINS = None          # None = toutes les feuilles « healthy » de FGVC8 ; sinon un plafond
ATLDSD_MODE = "train"           # images ATLDSD/PlantVillage d'AppleLeaf9 (aucune feuille saine de cette source) :
                                #   "train"   : entraînement seulement (pas évaluées, le raccourci ne gonfle pas le test)
                                #   "exclure" : écartées
                                #   "tout"    : réparties comme les autres (déconseillé)

ON_KAGGLE = Path("/kaggle").exists()
WORK = Path("/kaggle/working/apple_prep") if ON_KAGGLE else Path("./apple_prep")
RAW = Path("/kaggle/temp/raw") if (ON_KAGGLE and Path("/kaggle/temp").exists()) else Path("./raw")
INPUT_ROOT = Path("/kaggle/input")

# Dossiers déjà présents (prioritaires sur le téléchargement). Exemple en local :
# LOCAL_DIRS = dict(appleleaf9=r"data\datasets\pommier\raw\appleleaf9", ...)
LOCAL_DIRS = dict(appleleaf9=None, fgvc8=None, plantdoc=None, gymnsa=None)

SOURCES = {
    "appleleaf9": dict(role="principal", licence="CC BY 4.0",
                       url="https://codeload.github.com/JasonYangCode/AppleLeaf9/tar.gz/refs/heads/main"),
    "fgvc8": dict(role="principal", licence="règlement de la compétition Kaggle",
                  kaggle_slug="plant-pathology-2021-fgvc8"),
    "plantdoc": dict(role="test_externe", licence="CC BY 4.0", repo="pratikkayal/PlantDoc-Dataset", branch="master",
                     dirs=["train/Apple leaf", "train/Apple Scab Leaf", "train/Apple rust leaf",
                           "test/Apple leaf", "test/Apple Scab Leaf", "test/Apple rust leaf"]),
    "gymnsa": dict(role="drone", licence="CC BY 4.0",
                   url="https://data.mendeley.com/public-files/datasets/44kjgc4gkc/files/"
                       "206680b4-d1a4-410c-b487-304953541d36/file_downloaded",
                   sha256="e8ddbccdc89fae32aa98c9feb4f970151bc2fbc1cda98b1f8e1a665a654d60f7"),
}

CLASSES = ["SAIN", "MALADE"]    # ordre fixe, repris par le notebook 02 et le RunLogger (positive_class = MALADE)

# %%
# ===== 2. OUTILS DE BASE =====
import os, re, io, json, shutil, random, hashlib, tarfile, zipfile, time, sys, urllib.parse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
from PIL import Image, ImageOps, ImageDraw
import requests

Image.MAX_IMAGE_PIXELS = None
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
UA = {"User-Agent": "apple-prep/1.0 (travail academique)"}
N_THREADS = min(8, (os.cpu_count() or 2) * 2)
RUN_COMPLET = (RUN_MODE == "complet")
S, M = CLASSES
assert RUN_MODE in ("inventaire", "complet"), "RUN_MODE doit valoir 'inventaire' ou 'complet'"
assert ATLDSD_MODE in ("train", "exclure", "tout"), "ATLDSD_MODE doit valoir 'train', 'exclure' ou 'tout'"
assert abs(sum(SPLIT) - 1) < 1e-9, "SPLIT doit sommer à 1"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


WORK.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
random.seed(SEED)
np.random.seed(SEED)
log("Python", sys.version.split()[0], "| Pillow", Image.__version__, "| pandas", pd.__version__,
    "| Kaggle" if ON_KAGGLE else "| local", "| WORK =", WORK)

# %%
# ===== 3. TÉLÉCHARGEMENTS (reprenables, extraction sécurisée) =====
def _safe_target(base, name):
    t = (Path(base) / name).resolve()
    if not str(t).startswith(str(Path(base).resolve())):
        raise ValueError(f"chemin dangereux dans l'archive : {name}")
    return t


def fetch_tar_gz(url, dest, strip=1):
    """Télécharge et décompresse une archive .tar.gz en flux (aucun fichier temporaire)."""
    with requests.get(url, headers=UA, stream=True, timeout=120) as r:
        r.raise_for_status()
        with tarfile.open(fileobj=r.raw, mode="r|gz") as tf:
            for m in tf:
                parts = m.name.split("/")[strip:]
                if not parts or not m.isfile():
                    continue
                t = _safe_target(dest, "/".join(parts))
                t.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as f, open(t, "wb") as o:
                    shutil.copyfileobj(f, o)


def fetch_file(url, dest, sha256=None):
    dest = Path(dest)
    if dest.exists() and (sha256 is None or _sha256(dest) == sha256):
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, headers=UA, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    if sha256 and _sha256(tmp) != sha256:
        raise RuntimeError(f"empreinte SHA-256 incorrecte pour {dest.name} : fichier corrompu ou modifié")
    tmp.replace(dest)
    return dest


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_unzip(zp, dest):
    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            _safe_target(dest, n)
        z.extractall(dest)


def count_images(p):
    return sum(1 for x in Path(p).rglob("*") if x.suffix.lower() in IMG_EXT)


def find_in_inputs(pattern_dir, min_images=10):
    """Cherche dans /kaggle/input un dossier dont le nom correspond (si l'utilisateur a ajouté la source en Input)."""
    if not INPUT_ROOT.exists():
        return None
    for d in INPUT_ROOT.rglob("*"):
        if d.is_dir() and re.search(pattern_dir, d.name, re.I) and count_images(d) >= min_images:
            return d
    return None


def get_appleleaf9():
    if LOCAL_DIRS["appleleaf9"]:
        return Path(LOCAL_DIRS["appleleaf9"])
    d = find_in_inputs(r"appleleaf9", 1000)
    if d:
        return d
    dest = RAW / "appleleaf9"
    if count_images(dest) >= 14000:
        return dest
    if not DOWNLOAD:
        raise FileNotFoundError("AppleLeaf9 introuvable : renseigne LOCAL_DIRS['appleleaf9'] ou active DOWNLOAD")
    log("téléchargement AppleLeaf9 (~1,1 Go) ...")
    fetch_tar_gz(SOURCES["appleleaf9"]["url"], dest)
    return dest


def get_fgvc8():
    """Renvoie (dossier des images, DataFrame image/labels). Cherche un train.csv avec une colonne « labels »."""
    cands = []
    if LOCAL_DIRS["fgvc8"]:
        cands.append(Path(LOCAL_DIRS["fgvc8"]))
    if INPUT_ROOT.exists():
        cands += [p.parent for p in INPUT_ROOT.rglob("train.csv")]
    for c in cands:
        csv = c / "train.csv"
        if not csv.exists():
            continue
        df = pd.read_csv(csv, dtype=str)
        if {"image", "labels"} <= set(df.columns):
            img_dir = c / "train_images"
            if img_dir.exists():
                return img_dir, df
    raise FileNotFoundError(
        "FGVC8 introuvable. Sur Kaggle : Add Input → compétition « plant-pathology-2021-fgvc8 » "
        "(accepter le règlement). En local : LOCAL_DIRS['fgvc8'] = dossier contenant train.csv et train_images/.")


def get_plantdoc():
    if LOCAL_DIRS["plantdoc"]:
        return Path(LOCAL_DIRS["plantdoc"])
    dest = RAW / "plantdoc_apple"
    cfg = SOURCES["plantdoc"]
    if count_images(dest) >= 250 or not DOWNLOAD:
        return dest
    log("téléchargement PlantDoc (pommier, ~270 images) ...")
    jobs = []
    for d in cfg["dirs"]:
        api = f"https://api.github.com/repos/{cfg['repo']}/contents/{urllib.parse.quote(d)}?ref={cfg['branch']}"
        for it in requests.get(api, headers=UA, timeout=60).json():
            if it.get("type") == "file":
                raw = (f"https://raw.githubusercontent.com/{cfg['repo']}/{cfg['branch']}/"
                       + urllib.parse.quote(it["path"]))
                jobs.append((raw, dest / it["path"]))

    def one(job):
        url, out = job
        if out.exists():
            return True
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            out.write_bytes(r.content)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(N_THREADS) as ex:
        ok = list(ex.map(one, jobs))
    log(f"PlantDoc : {sum(ok)}/{len(ok)} fichiers")
    return dest


def get_gymnsa():
    if LOCAL_DIRS["gymnsa"]:
        return Path(LOCAL_DIRS["gymnsa"])
    dest = RAW / "gymnsa"
    if count_images(dest) >= 700:
        return dest
    if not DOWNLOAD:
        raise FileNotFoundError("GYMNSA introuvable : renseigne LOCAL_DIRS['gymnsa'] ou active DOWNLOAD")
    log("téléchargement GYMNSA (204 Mo, empreinte vérifiée) ...")
    zp = fetch_file(SOURCES["gymnsa"]["url"], RAW / "GYMNSA_dataset.zip", SOURCES["gymnsa"]["sha256"])
    safe_unzip(zp, dest)
    return dest

# %%
# ===== 4. EMPREINTES, TAILLE, QUALITÉ JPEG =====
# Table de quantification luminance standard (IJG, qualité 50), pour estimer la qualité d'un JPEG.
_STD_LUMA = np.array([16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
                      14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
                      49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], dtype=float)
_ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14,
           21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53,
           60, 61, 54, 47, 55, 62, 63]


def jpeg_quality(im):
    """Qualité IJG la plus proche de la table de quantification luminance (None si pas un JPEG)."""
    q = getattr(im, "quantization", None)
    if not q or 0 not in q:
        return None
    t = np.array(list(q[0]), dtype=float)
    if len(t) != 64:
        return None
    best, err = None, 1e18
    for quality in range(1, 101):
        sc = 5000 / quality if quality < 50 else 200 - 2 * quality
        ref = np.clip(np.floor((_STD_LUMA * sc + 50) / 100), 1, 255)
        for order in (ref, ref[_ZIGZAG]):       # Pillow peut rendre la table en ordre naturel ou zigzag
            e = float(np.abs(order - t).sum())
            if e < err:
                best, err = quality, e
    return best


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_info(path):
    """Taille, qualité JPEG, md5 et 8 empreintes dHash 64 bits (rotations/miroirs : une copie tournée reste un doublon)."""
    try:
        with Image.open(path) as im:
            w, h = im.size
            q = jpeg_quality(im)
            if im.format == "JPEG":
                im.draft("L", (64, 64))
            g = im.convert("L").resize((9, 9), Image.BILINEAR)
        a = np.asarray(g, dtype=np.int16)
        hs = []
        for k in range(4):
            for flip in (False, True):
                t = np.rot90(a, k)
                t = t[:, ::-1] if flip else t
                bits = (t[:8, 1:] > t[:8, :-1]).astype(np.uint8).ravel()
                hs.append(int(np.frombuffer(np.packbits(bits).tobytes(), dtype=">u8")[0]))
        return dict(ok=True, width=w, height=h, jpeg_q=q, md5=file_md5(path), hashes=hs)
    except Exception as e:
        return dict(ok=False, error=type(e).__name__)


def cluster_duplicates(H, T):
    """Union-find sur les paires d'images à distance de Hamming <= T, toutes rotations confondues.
    Recherche par morceaux de bits : si <= T bits diffèrent, au moins un des T+1 morceaux est identique."""
    n = len(H)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    nch = T + 1
    bounds = [(64 * c) // nch for c in range(nch + 1)]
    buckets = [defaultdict(list) for _ in range(nch)]
    for i in range(n):
        for k in range(8):
            v = H[i][k]
            for c in range(nch):
                lo, hi = bounds[c], bounds[c + 1]
                buckets[c][(v >> lo) & ((1 << (hi - lo)) - 1)].append((i, k))
    skipped = 0
    for i in range(n):
        h0 = H[i][0]
        for c in range(nch):
            lo, hi = bounds[c], bounds[c + 1]
            lst = buckets[c].get((h0 >> lo) & ((1 << (hi - lo)) - 1), ())
            if len(lst) > 4000:
                skipped += 1
                continue
            for j, k in lst:
                if j > i and bin(h0 ^ H[j][k]).count("1") <= T:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
    if skipped:
        log(f"(attention : {skipped} paquets d'empreintes trop gros ignorés — images peu texturées)")
    return [find(i) for i in range(n)]


def appleleaf9_subsource(w, h):
    """Origine probable d'une image AppleLeaf9 d'après sa taille (vérifiée sur les fichiers le 30/10/2026)."""
    lo, hi = sorted((w, h))
    if (hi, lo) == (2048, 1365):
        return "fgvc2020"
    if lo == 640 and hi in (853, 958, 960):
        return "fgvc2021"
    return "atldsd_pvd"

# %%
# ===== 5. LISTE DES IMAGES (manifeste brut) =====
def rec(source, sous_source, path, root, fine, binary, split_impose=None, n_boxes=None, reason=None):
    return dict(source=source, sous_source=sous_source, role=SOURCES[source]["role"], path=str(path),
                rel=str(Path(path).relative_to(root)), fine=fine, binary=binary, split_impose=split_impose,
                n_boxes=n_boxes, reason=reason)


def scan_appleleaf9(root):
    rows = []
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        for p in sorted(d.iterdir()):
            if p.suffix.lower() in IMG_EXT:
                rows.append(rec("appleleaf9", None, p, root, d.name, S if d.name.lower() == "health" else M))
    return rows


def scan_fgvc8(img_dir, df):
    df = df.copy()
    df["labels"] = df["labels"].fillna("").str.strip()
    log("FGVC8 : étiquettes du train.csv (une image peut en avoir plusieurs) :")
    print(df["labels"].value_counts().head(12).to_string())
    healthy = df[df["labels"] == "healthy"]
    if FGVC8_MAX_SAINS and len(healthy) > FGVC8_MAX_SAINS:
        healthy = healthy.sample(FGVC8_MAX_SAINS, random_state=SEED)
    rows, missing = [], 0
    for name in healthy["image"]:
        p = Path(img_dir) / name
        if p.exists():
            rows.append(rec("fgvc8", "fgvc2021", p, img_dir, "healthy", S))
        else:
            missing += 1
    log(f"FGVC8 : {len(rows)} feuilles saines retenues ({missing} fichiers absents) ; les autres classes ne sont pas utilisées")
    return rows


def scan_plantdoc(root):
    rows = []
    for p in sorted(Path(root).rglob("*")):
        if p.suffix.lower() in IMG_EXT:
            cls = p.parent.name
            rows.append(rec("plantdoc", "web", p, root, cls, S if cls.lower() == "apple leaf" else M,
                            split_impose="test_externe"))
    return rows


def scan_gymnsa(root):
    rows = []
    for p in sorted(Path(root).rglob("*")):
        if p.suffix.lower() not in IMG_EXT or p.parent.name != "images":
            continue
        split = p.parent.parent.name.lower()                       # train / val (découpage des auteurs)
        lab = p.parent.parent / "labels" / (p.stem + ".txt")
        if not lab.exists():
            rows.append(rec("gymnsa", "drone_poirier", p, root, None, None, reason="étiquette YOLO absente"))
            continue
        n = sum(1 for line in lab.read_text().splitlines() if line.strip())
        rows.append(rec("gymnsa", "drone_poirier", p, root, "rouille_poirier" if n else "sans_symptome",
                        M if n else S, split_impose="drone_" + split, n_boxes=n))
    return rows

# %%
# ===== 6. OBTENIR LES SOURCES + INVENTAIRE =====
def prepare_sources():
    roots, rows = {}, []
    roots["appleleaf9"] = get_appleleaf9()
    rows += scan_appleleaf9(roots["appleleaf9"])
    img_dir, fdf = get_fgvc8()
    roots["fgvc8"] = img_dir
    rows += scan_fgvc8(img_dir, fdf)
    for name, getter, scanner in (("plantdoc", get_plantdoc, scan_plantdoc), ("gymnsa", get_gymnsa, scan_gymnsa)):
        try:
            roots[name] = getter()
            rows += scanner(roots[name])
        except Exception as e:                    # sources secondaires : on continue sans elles, mais on le dit
            log(f"ATTENTION : {name} indisponible ({type(e).__name__}: {e}) — poursuite sans cette source")
    df = pd.DataFrame(rows)
    for k, v in roots.items():
        log(f"{k:11s} {v}")
    print(df.groupby(["source", "fine", "binary"], dropna=False).size().to_string())
    return df


def describe_sizes(df, n=200):
    """Inventaire : tailles et qualité JPEG sur un échantillon par (source, étiquette fine)."""
    out = []
    for (s, f), g in df.groupby(["source", "fine"], dropna=False):
        pick = g.sample(min(n, len(g)), random_state=SEED)
        infos = [image_info(p) for p in pick["path"]]
        sizes = Counter((i.get("width"), i.get("height")) for i in infos if i["ok"])
        qs = Counter(i.get("jpeg_q") for i in infos if i["ok"])
        out.append(dict(source=s, fine=f, n=len(g), tailles=sizes.most_common(3), qualite_jpeg=qs.most_common(2)))
    print(pd.DataFrame(out).to_string(index=False))


RAW_DF = prepare_sources()
if not RUN_COMPLET:
    describe_sizes(RAW_DF)
    log("Mode inventaire terminé. Vérifie les effectifs ci-dessus, puis passe RUN_MODE = 'complet'.")

# %%
# ===== 7. VALIDATION, SOUS-SOURCES, DOUBLONS =====
def validate(df):
    log(f"lecture et empreintes de {len(df)} images ...")
    with ThreadPoolExecutor(N_THREADS) as ex:
        infos = list(ex.map(image_info, df["path"].tolist()))
    df = df.copy()
    for k in ("ok", "width", "height", "jpeg_q", "md5"):
        df[k] = [i.get(k) for i in infos]
    df["hashes"] = [i.get("hashes") for i in infos]
    df.loc[~df["ok"].astype(bool), "reason"] = "image illisible"
    small = df["ok"].astype(bool) & ((df["width"] < MIN_SIDE) | (df["height"] < MIN_SIDE))
    df.loc[small & df["reason"].isna(), "reason"] = f"trop petite (< {MIN_SIDE} px)"
    al9 = (df["source"] == "appleleaf9") & df["ok"].astype(bool)
    df.loc[al9, "sous_source"] = [appleleaf9_subsource(w, h) for w, h in zip(df.loc[al9, "width"], df.loc[al9, "height"])]
    return df


def dedupe(df):
    """Doublons exacts (md5) et quasi-doublons (empreintes) entre toutes les sources « feuille ».
    Conflit d'étiquettes → quarantaine. Sinon on garde une seule copie, avec cette priorité :
    jeu principal > test externe (le test externe doit rester indépendant), puis la plus grande image."""
    df = df.copy()
    cand = df.index[df["reason"].isna() & (df["role"] != "drone")].tolist()
    cl = cluster_duplicates([df.at[k, "hashes"] for k in cand], DUP_HAMMING)
    cid = dict(zip(cand, cl))
    first_md5 = {}
    for k in cand:                                   # fusionne aussi les fichiers strictement identiques
        m = df.at[k, "md5"]
        if m in first_md5:
            cid[k] = cid[first_md5[m]]
        else:
            first_md5[m] = k
    df["dup_cluster"] = -1
    for k, c in cid.items():
        df.at[k, "dup_cluster"] = c
    sub = df.loc[cand]
    conflicts = 0
    for c, g in sub.groupby("dup_cluster"):
        if len(g) > 1 and g["binary"].nunique() > 1:
            df.loc[g.index, "reason"] = "conflit d'étiquettes entre doublons"
            conflicts += len(g)
    sub = df.loc[cand]
    sub = sub[sub["reason"].isna()]
    sub = sub.assign(prio=(sub["role"] == "principal").astype(int), pix=sub["width"] * sub["height"])
    keep = sub.sort_values(["prio", "pix"], ascending=False).groupby("dup_cluster").head(1).index
    dropped = sub.index.difference(keep)
    df.loc[dropped, "reason"] = "doublon (copie écartée)"
    pairs = Counter()
    for c, g in sub.groupby("dup_cluster"):
        if len(g) > 1:
            pairs[" + ".join(sorted(set(g["source"] + ":" + g["sous_source"].fillna("?"))))] += 1
    log(f"doublons écartés : {len(dropped)} ; images en conflit d'étiquettes : {conflicts}")
    if pairs:
        print("grappes de doublons par combinaison de sources :")
        print(pd.Series(pairs).sort_values(ascending=False).to_string())
    return df

# %%
# ===== 8. DÉCOUPAGE SANS FUITE =====
def assign_splits(df):
    """Jeu principal : 70/15/15 stratifié par (sous-source, classe). Les images ATLDSD suivent ATLDSD_MODE.
    PlantDoc → test_externe ; GYMNSA → découpage des auteurs (drone_train / drone_val)."""
    df = df.copy()
    df["split"] = None
    ok = df["reason"].isna() & df["binary"].notna()
    imp = ok & df["split_impose"].notna()
    df.loc[imp, "split"] = df.loc[imp, "split_impose"]
    main = ok & (df["role"] == "principal")
    atl = main & (df["sous_source"] == "atldsd_pvd")
    if ATLDSD_MODE == "exclure":
        df.loc[atl, "reason"] = "ATLDSD/PlantVillage exclu (ATLDSD_MODE='exclure')"
    elif ATLDSD_MODE == "train":
        df.loc[atl, "split"] = "train"
    todo = main & df["split"].isna() & df["reason"].isna()
    r = random.Random(SEED)
    for (ss, b), g in df[todo].groupby(["sous_source", "binary"]):
        idx = list(g.index)
        r.shuffle(idx)
        n = len(idx)
        n_tr, n_va = round(SPLIT[0] * n), round(SPLIT[1] * n)
        df.loc[idx[:n_tr], "split"] = "train"
        df.loc[idx[n_tr:n_tr + n_va], "split"] = "val"
        df.loc[idx[n_tr + n_va:], "split"] = "test"
    return df


def check_no_leak(df):
    d = df[df["split"].notna()]
    c = d[d["dup_cluster"] >= 0].groupby("dup_cluster")["split"].nunique()
    assert (c <= 1).all(), "FUITE : des doublons sont dans plusieurs ensembles"
    m = d.groupby("md5")["split"].nunique()
    assert (m <= 1).all(), "FUITE : fichiers identiques dans plusieurs ensembles"
    if ATLDSD_MODE == "train":
        bad = d[(d["sous_source"] == "atldsd_pvd") & (d["split"] != "train")]
        assert bad.empty, "FUITE : image ATLDSD hors entraînement alors que ATLDSD_MODE='train'"
    assert not d[(d["source"] == "plantdoc") & (d["split"] != "test_externe")].shape[0], "PlantDoc hors test externe"
    log("contrôle anti-fuite : OK (doublons, fichiers identiques, sources à rôle imposé)")


def check_shortcuts(df):
    """Raccourci de source : une sous-source évaluée qui ne contient qu'une seule classe.
    Renvoie la table sous-source × classe sur train/val/test."""
    d = df[df["split"].isin(["train", "val", "test"])]
    tab = d.groupby(["sous_source", "binary"]).size().unstack(fill_value=0).reindex(columns=CLASSES, fill_value=0)
    print("\n===== RACCOURCIS DE SOURCE : sous-source × classe (train/val/test) =====")
    print(tab.to_string())
    d_all = df[df["split"].notna()]
    print("\n===== FORMAT D'ORIGINE (avant harmonisation) : taille et qualité JPEG les plus fréquentes =====")
    print(d_all.groupby(["sous_source", "binary"]).agg(
        n=("path", "size"),
        taille=("width", lambda s: f"{s.mode().iat[0]}×{d_all.loc[s.index, 'height'].mode().iat[0]}"),
        jpeg_q=("jpeg_q", lambda s: s.mode().iat[0] if s.notna().any() else None)).to_string())
    print("(Les différences visibles ici sont effacées par l'harmonisation : même taille et même JPEG pour tous.)")
    ev = df[df["split"].isin(["val", "test"])]
    for ss, g in ev.groupby("sous_source"):
        if g["binary"].nunique() < 2:
            log(f"ATTENTION : la sous-source « {ss} » n'a qu'une classe en val/test → métriques à lire par sous-source")
    return tab

# %%
# ===== 9. EXPORT =====
_HQ = {}


def harmonize_quality(df):
    """Qualité JPEG cible : celle des images FGVC2021 d'AppleLeaf9 (sauf réglage manuel)."""
    if HARMONIZE_QUALITY:
        return int(HARMONIZE_QUALITY)
    q = df[(df["source"] == "appleleaf9") & (df["sous_source"] == "fgvc2021")]["jpeg_q"].dropna()
    val = int(q.median()) if len(q) else 75
    log(f"qualité JPEG d'harmonisation estimée sur AppleLeaf9/FGVC2021 : {val}")
    return val


def letterbox(im, size):
    w, h = im.size
    s = size / max(w, h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    canvas.paste(im.resize((nw, nh), Image.LANCZOS), ((size - nw) // 2, (size - nh) // 2))
    return canvas


def harmonize(im, quality):
    """Même traitement pour toutes les images du jeu principal : côté long HARMONIZE_LONG_SIDE puis JPEG `quality`."""
    w, h = im.size
    if max(w, h) > HARMONIZE_LONG_SIDE:
        s = HARMONIZE_LONG_SIDE / max(w, h)
        im = im.convert("RGB").resize((round(w * s), round(h * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def out_name(r):
    key = hashlib.md5((r["source"] + "/" + r["rel"]).encode()).hexdigest()[:8]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(r["rel"]).stem)[:50]
    return f"{r['source']}__{stem}__{key}.jpg"


def export_one(r):
    name = out_name(r)
    if r["role"] == "drone":
        sp = r["split"].replace("drone_", "")
        out = WORK / "drone" / "cls" / sp / r["binary"] / name
    else:
        out = WORK / "cls" / r["split"] / r["binary"] / name
    if not out.exists():
        with Image.open(r["path"]) as im:
            w, h = im.size
            if r["role"] == "principal" and im.format == "JPEG" and max(w, h) > 2 * HARMONIZE_LONG_SIDE:
                # décodage JPEG réduit (rapide) ; reste au moins 2× plus grand que la cible avant le redimensionnement
                s = 2 * HARMONIZE_LONG_SIDE / max(w, h)
                im.draft("RGB", (int(w * s) + 1, int(h * s) + 1))
            im = ImageOps.exif_transpose(im)
            if r["role"] in ("principal", "drone"):
                # GYMNSA : tuiles « fond » en JPEG ~100, tuiles malades en JPEG 75 → même compression pour toutes
                im = harmonize(im, _HQ["q"])
            lb = letterbox(im.convert("RGB"), IMG_SIZE)
        out.parent.mkdir(parents=True, exist_ok=True)
        lb.save(out, "JPEG", quality=92)
    if r["role"] == "drone":                       # tuiles 768 harmonisées + boîtes YOLO (détection, classe 0 = malade)
        sp = r["split"].replace("drone_", "")
        src = Path(r["path"])
        di, dl = WORK / "drone" / "det" / sp / "images", WORK / "drone" / "det" / sp / "labels"
        di.mkdir(parents=True, exist_ok=True)
        dl.mkdir(parents=True, exist_ok=True)
        dst = di / (src.stem + ".jpg")
        if not dst.exists():
            with Image.open(src) as im:               # tuiles sans rotation EXIF : les boîtes restent valides
                harmonize(im, _HQ["q"]).save(dst, "JPEG", quality=95)
            shutil.copy2(src.parent.parent / "labels" / (src.stem + ".txt"), dl / (src.stem + ".txt"))
    return str(out.relative_to(WORK))


def export_all(df):
    _HQ["q"] = harmonize_quality(df)
    d = df[df["split"].notna()]
    log(f"export de {len(d)} images (harmonisation + format {IMG_SIZE}×{IMG_SIZE}) ...")
    with ThreadPoolExecutor(N_THREADS) as ex:
        outs = list(ex.map(export_one, d.to_dict("records")))
    df = df.copy()
    df["out_path"] = None
    df.loc[d.index, "out_path"] = outs
    if (WORK / "drone" / "det").exists():
        (WORK / "drone" / "det" / "dataset.yaml").write_text(
            f"path: {WORK / 'drone' / 'det'}\ntrain: train/images\nval: val/images\nnames:\n  0: malade\n")
    return df


def visual_check(df):
    qc = WORK / "qc"
    qc.mkdir(exist_ok=True)
    d = df[df["split"].notna()]
    for (ss, b), g in d.groupby(["sous_source", "binary"]):
        pick = g.sample(min(6, len(g)), random_state=SEED)
        tiles = [Image.open(WORK / p).resize((192, 192)) for p in pick["out_path"]]
        sheet = Image.new("RGB", (192 * max(1, len(tiles)), 192), (255, 255, 255))
        for i, t in enumerate(tiles):
            sheet.paste(t, (192 * i, 0))
        sheet.save(qc / f"{ss}_{b}.jpg", quality=85)
    log("planches de contrôle (une par sous-source et classe) :", qc)

# %%
# ===== 10. LANCEMENT + RAPPORTS =====
def run_pipeline(df):
    df = validate(df)
    df = dedupe(df)
    df = assign_splits(df)
    check_no_leak(df)
    tab_sc = check_shortcuts(df)
    df = export_all(df)
    visual_check(df)
    used = df[df["split"].notna()].copy()
    used["id"] = [Path(p).stem for p in used["out_path"]]
    assert used["id"].is_unique, "identifiants d'images non uniques"
    cols = ["id", "out_path", "split", "binary", "fine", "source", "sous_source", "role", "rel",
            "width", "height", "jpeg_q", "md5", "dup_cluster", "n_boxes"]
    used[cols].to_csv(WORK / "manifest.csv", index=False)
    q = df[df["split"].isna()]
    q[["source", "sous_source", "rel", "fine", "reason"]].to_csv(WORK / "quarantaine.csv", index=False)
    eff = used.groupby(["source", "sous_source", "split", "binary"]).size().unstack("binary", fill_value=0)
    eff = eff.reindex(columns=CLASSES, fill_value=0)
    eff.to_csv(WORK / "effectifs.csv")
    tab_sc.to_csv(WORK / "raccourcis_sous_source.csv")
    (WORK / "classes.json").write_text(json.dumps(
        {"classes": CLASSES, "label_mode": "single", "positive_class": M}, ensure_ascii=False, indent=2))
    print("\n===== EFFECTIFS par source / sous-source / ensemble / classe =====")
    print(eff.to_string())
    print("\n===== TOTAL par ensemble =====")
    print(used.groupby(["split", "binary"]).size().unstack(fill_value=0).reindex(columns=CLASSES, fill_value=0).to_string())
    print("\n===== QUARANTAINE / REJETS (motif) =====")
    print(q.groupby(["source", "reason"], dropna=False).size().to_string() if len(q) else "(aucun)")
    (WORK / "README_dataset.md").write_text(
        "# Jeu de données pommier — préparé par 01_preparation_donnees\n\n"
        f"- SEED={SEED}, IMG_SIZE={IMG_SIZE}, HARMONIZE_LONG_SIDE={HARMONIZE_LONG_SIDE}, "
        f"qualité JPEG={_HQ['q']}, DUP_HAMMING={DUP_HAMMING}, SPLIT={SPLIT}, ATLDSD_MODE={ATLDSD_MODE}\n"
        "- `cls/{train,val,test}/{SAIN,MALADE}/` : jeu principal (AppleLeaf9 + FGVC8 sains), harmonisé\n"
        "- `cls/test_externe/{SAIN,MALADE}/` : PlantDoc, jamais utilisé pour entraîner ni régler\n"
        "- `drone/cls/{train,val}/{SAIN,MALADE}/` et `drone/det/` (YOLO, 0 = malade) : GYMNSA (poirier, drone)\n"
        "- `manifest.csv` : une ligne par image exportée (id, chemin, ensemble, classe, source, sous-source…)\n"
        "- `classes.json` : ordre des classes et classe positive (pour le RunLogger)\n"
        "- `quarantaine.csv` : images écartées et motif ; `effectifs.csv` ; `raccourcis_sous_source.csv`\n"
        "- Licences : AppleLeaf9, PlantDoc, GYMNSA en CC BY 4.0 (citer les auteurs) ; FGVC8 : règlement Kaggle\n")
    return df


if RUN_COMPLET:
    MANIFEST = run_pipeline(RAW_DF)
    log("Terminé. Résultats dans", WORK, "→ « Save Version » pour les utiliser dans le notebook 02.")
