# %% [markdown]
# # Livrable 2 — Préparation des données maïs (SAIN / MALADE_OU_RAVAGEUR)
#
# **Ce notebook** télécharge (un sous-échantillon de) jeux de données publics sur le maïs, harmonise les
# classes vers `SAIN` / `MALADE_OU_RAVAGEUR`, nettoie, dédoublonne, découpe en train/val/test **sans fuite**
# et exporte (1) un jeu de classification et (2) un jeu de détection (boîtes) quand des boîtes existent.
#
# **Réglages Kaggle (panneau de droite)** : Accelerator = *None* (le CPU suffit, ça ne consomme aucune heure de GPU),
# Internet = *On* (nécessite un compte vérifié par téléphone).
#
# **Deux passes :**
# 1. `RUN_MODE = "inventaire"` : télécharge un échantillon et décrit les fichiers reçus (arborescence, extensions,
#    extraits d'annotations). Aucun traitement. Lis le résultat : les formats des jeux n'ont pas pu être vérifiés
#    avant exécution.
# 2. `RUN_MODE = "complet"` : prépare tout. Regarde les rapports « quarantaine » et « mapping » avant de continuer.
#
# Chaque étape est reprenable : les téléchargements et les images déjà exportées ne sont pas refaits.

# %%
# ===== 1. PARAMÈTRES (c'est la seule cellule à modifier) =====
from pathlib import Path

RUN_MODE = "inventaire"      # "inventaire" (décrire) ou "complet" (préparer)
DOWNLOAD = True              # False si tu as ajouté les jeux comme « Input » Kaggle ou posé les fichiers à la main
SEED = 42
IMG_SIZE = 512               # côté des images exportées (carré, bandes grises si besoin)
MIN_SIDE = 96                # images dont un côté est plus petit : rejetées
DUP_HAMMING = 4              # deux images à distance de hachage <= cette valeur (sur 64 bits) sont des doublons
MAX_PER_CLASS_PER_SOURCE = 6000   # plafond par (source, classe binaire) après nettoyage
SPLIT = (0.70, 0.15, 0.15)   # train / val / test
MAX_RAW_GB = 18              # garde-fou : on n'écrit pas plus que cela de données brutes

ON_KAGGLE = Path("/kaggle").exists()
WORK = Path("/kaggle/working/maize_prep") if ON_KAGGLE else Path("./maize_prep")
RAW = Path("/kaggle/temp/raw") if (ON_KAGGLE and Path("/kaggle/temp").exists()) else Path("./raw")
INPUT_ROOT = Path("/kaggle/input")

# Sources (licences vérifiées sur les fiches, voir SOURCES.csv).
# local_dir : chemin d'un dossier déjà présent (sinon téléchargement ou recherche dans /kaggle/input).
# max_images : nombre maximal d'images tirées au hasard au téléchargement.
SOURCES = {
    "karaagro": dict(enabled=True, domain="champ", train_only=False, licence="CC0 1.0",
                     dataverse_doi="doi:10.7910/DVN/CXUMDS", max_images=9000, local_dir=None),
    "makerere": dict(enabled=True, domain="champ", train_only=False, licence="CC0 1.0",
                     dataverse_doi="doi:10.7910/DVN/LPGHKK", max_images=9000, local_dir=None),
    "mld_bangladesh": dict(enabled=True, domain="champ", train_only=False, licence="CC BY 4.0",
                           mendeley_id="3myfctrgk3", max_images=3000, local_dir=None),
    "plantdoc": dict(enabled=True, domain="web", train_only=False, licence="CC BY 4.0",
                     zip_url="https://codeload.github.com/pratikkayal/PlantDoc-Object-Detection-Dataset/zip/refs/heads/master",
                     class_filter=r"corn|maize", max_images=3000, local_dir=None),
    # PlantVillage (photos de laboratoire) : seulement pour l'entraînement, jamais en val/test.
    # Pas de téléchargement automatique : pose les fichiers dans un dossier et renseigne local_dir.
    "plantvillage": dict(enabled=False, domain="labo", train_only=True, licence="?",
                         class_filter=r"corn|maize", max_images=3000, local_dir=None),
}

# Jeu drone Cornell (50 Go) : on n'en lit qu'un petit échantillon pour inspecter le format (mode inventaire).
CORNELL = dict(enabled=False,
               url="https://download.cncb.ac.cn//OPIA/DiseaseNLBdrone.zip",
               sample_images=40)

# %%
# ===== 2. OUTILS DE BASE =====
import os, re, io, json, math, shutil, random, hashlib, zipfile, time, sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
from PIL import Image, ImageOps, ImageDraw
import requests
try:
    import yaml
except ImportError:
    yaml = None

Image.MAX_IMAGE_PIXELS = None            # grandes images de drone
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
UA = {"User-Agent": "maize-prep/1.0 (travail academique)"}
N_THREADS = min(8, (os.cpu_count() or 2) * 2)
RUN_COMPLET = (RUN_MODE == "complet")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def free_gb(p):
    return shutil.disk_usage(p).free / 1e9


WORK.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)
random.seed(SEED)
np.random.seed(SEED)


def check_env():
    log("Python", sys.version.split()[0], "| Pillow", Image.__version__, "| numpy", np.__version__, "| pandas", pd.__version__)
    log(f"Disque libre : WORK {free_gb(WORK):.1f} Go | RAW {free_gb(RAW):.1f} Go | threads {N_THREADS}")
    try:
        r = requests.get("https://dataverse.harvard.edu", timeout=10, headers=UA)
        log("Internet : OK (code", r.status_code, ")")
    except Exception as e:
        log("Internet : INDISPONIBLE (", type(e).__name__, "). Active « Internet » dans Kaggle, ou utilise DOWNLOAD=False.")


check_env()

# %%
# ===== 3. OUTILS RÉSEAU : téléchargement, zip distant lu à la demande =====
DATAVERSE = "https://dataverse.harvard.edu"


def get_json(url, **kw):
    r = requests.get(url, headers=UA, timeout=60, **kw)
    r.raise_for_status()
    return r.json()


def safe_join(base, name):
    """Chemin de sortie sûr (refuse '..' et chemins absolus)."""
    parts = [p for p in Path(str(name).replace("\\", "/")).parts if p not in ("", ".", "..", "/")]
    return Path(base).joinpath(*parts)


def download_file(url, dest, expected_size=None, retries=4):
    """Téléchargement avec reprise (Range) et nouvelle tentative."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (expected_size is None or dest.stat().st_size == expected_size):
        return dest
    tmp = dest.with_name(dest.name + ".part")
    last = None
    for k in range(retries):
        try:
            pos = tmp.stat().st_size if tmp.exists() else 0
            h = dict(UA)
            if pos:
                h["Range"] = f"bytes={pos}-"
            with requests.get(url, headers=h, stream=True, timeout=60) as r:
                if r.status_code == 416:      # déjà complet
                    break
                r.raise_for_status()
                mode = "ab" if (pos and r.status_code == 206) else "wb"
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            break
        except Exception as e:
            last = e
            time.sleep(2 * (k + 1))
    else:
        raise RuntimeError(f"échec du téléchargement de {url} : {last}")
    tmp.replace(dest)
    return dest


class RangeFile(io.RawIOBase):
    """Fichier distant en lecture seule (requêtes HTTP Range) : permet d'ouvrir un gros zip sans le télécharger."""

    def __init__(self, url, block=1 << 20):
        super().__init__()
        self.url, self.block, self.pos = url, block, 0
        self.cache_start, self.cache = 0, b""
        self._resolve()

    def _resolve(self):
        r = requests.get(self.url, headers={**UA, "Range": "bytes=0-0"}, stream=True, timeout=60)
        try:
            if r.status_code != 206:
                raise RuntimeError(f"Le serveur n'accepte pas les requêtes Range (code {r.status_code})")
            self.size = int(r.headers["Content-Range"].split("/")[-1])
            self.final_url = r.url
        finally:
            r.close()

    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos

    def seek(self, off, whence=0):
        self.pos = off if whence == 0 else (self.pos + off if whence == 1 else self.size + off)
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0 or self.pos + n > self.size:
            n = self.size - self.pos
        if n <= 0:
            return b""
        end = self.pos + n
        if not (self.cache_start <= self.pos and end <= self.cache_start + len(self.cache)):
            stop = min(self.size, self.pos + max(n, self.block))
            hdr = {**UA, "Range": f"bytes={self.pos}-{stop - 1}"}
            r = requests.get(self.final_url, headers=hdr, timeout=120)
            if r.status_code in (400, 401, 403):      # URL signée expirée : on la renouvelle
                self._resolve()
                r = requests.get(self.final_url, headers=hdr, timeout=120)
            if r.status_code != 206:
                raise RuntimeError(f"lecture Range échouée (code {r.status_code})")
            self.cache_start, self.cache = self.pos, r.content
        a = self.pos - self.cache_start
        data = self.cache[a:a + n]
        self.pos += len(data)
        return data

    def readinto(self, b):
        d = self.read(len(b))
        b[:len(d)] = d
        return len(d)


def _open_zip_source(src):
    return RangeFile(src) if str(src).startswith("http") else open(src, "rb")


def zip_summary(src):
    """Décrit un zip (local ou distant) sans l'extraire."""
    zf = zipfile.ZipFile(_open_zip_source(src))
    infos = [i for i in zf.infolist() if not i.is_dir()]
    ext = Counter(Path(i.filename).suffix.lower() for i in infos)
    top = Counter(Path(i.filename).parts[0] if len(Path(i.filename).parts) > 1 else "(racine)" for i in infos)
    return dict(n_files=len(infos), total_gb=sum(i.file_size for i in infos) / 1e9, ext=dict(ext),
                top_dirs=dict(top.most_common(15)), sample=[i.filename for i in infos[:10]])


def zip_extract_subset(src, dest, max_images, seed=SEED, small_mb=5, workers=N_THREADS):
    """Extrait d'un zip (URL ou fichier local) : max_images images tirées au hasard + leurs fichiers
    d'annotations + les petits fichiers utiles (yaml, csv, json, classes.txt...)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(_open_zip_source(src))
    infos = [i for i in zf.infolist() if not i.is_dir()]
    img_names = sorted(i.filename for i in infos if Path(i.filename).suffix.lower() in IMG_EXT)
    r = random.Random(seed)
    r.shuffle(img_names)
    chosen = img_names[:max_images]
    chosen_stems = {Path(n).stem for n in chosen}
    all_stems = {Path(n).stem for n in img_names}
    keep = []
    for i in infos:
        ext = Path(i.filename).suffix.lower()
        if ext in IMG_EXT or i.file_size > small_mb * 1e6:
            continue
        if ext in {".txt", ".xml"}:
            st = Path(i.filename).stem
            if st in all_stems and st not in chosen_stems:
                continue                       # annotation d'une image non retenue
        keep.append(i.filename)
    todo = chosen + keep
    sizes = {i.filename: i.file_size for i in infos}
    log(f"zip : {len(infos)} fichiers ; extraction de {len(chosen)} images + {len(keep)} fichiers annexes")

    def work(chunk):
        z2 = zipfile.ZipFile(_open_zip_source(src))
        n = 0
        for name in chunk:
            out = safe_join(dest, name)
            if out.exists() and out.stat().st_size == sizes[name]:
                n += 1
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(3):
                try:
                    with z2.open(name) as s, open(out, "wb") as d:
                        shutil.copyfileobj(s, d, 1 << 20)
                    n += 1
                    break
                except Exception:
                    time.sleep(1 + attempt)
        return n

    chunks = [todo[k::workers] for k in range(workers)]
    with ThreadPoolExecutor(workers) as ex:
        done = sum(ex.map(work, chunks))
    log(f"zip : {done}/{len(todo)} fichiers extraits vers {dest}")
    return dest


def unpack_nested(dest):
    """Extrait les zips imbriqués trouvés dans dest (puis les supprime)."""
    for z in list(Path(dest).rglob("*.zip")):
        try:
            zip_extract_subset(str(z), z.parent / z.stem, max_images=10 ** 9)
            z.unlink()
        except Exception as e:
            log("zip imbriqué ignoré :", z, e)


def fetch_dataverse(doi, dest, max_images):
    meta = get_json(f"{DATAVERSE}/api/datasets/:persistentId/", params={"persistentId": doi})
    files = meta["data"]["latestVersion"]["files"]
    rows = [dict(id=f["dataFile"]["id"], name=f["dataFile"]["filename"], dir=f.get("directoryLabel", ""),
                 size=f["dataFile"].get("filesize", 0)) for f in files if not f.get("restricted")]
    log(f"Dataverse {doi} : {len(rows)} fichiers, {sum(r['size'] for r in rows) / 1e9:.1f} Go au total")
    dest = Path(dest)
    zips = [r for r in rows if r["name"].lower().endswith(".zip")]
    loose = [r for r in rows if r not in zips]
    for z in zips:
        url = f"{DATAVERSE}/api/access/datafile/{z['id']}"
        try:
            zip_extract_subset(url, dest / z["dir"], max_images)
        except RuntimeError as e:
            log("lecture à la demande impossible :", e)
            if z["size"] / 1e9 <= MAX_RAW_GB:
                tmp = download_file(url, RAW / "_zips" / z["name"], z["size"])
                zip_extract_subset(str(tmp), dest / z["dir"], max_images)
                tmp.unlink()
            else:
                log(f"{z['name']} ({z['size'] / 1e9:.1f} Go) trop gros : ajoute-le comme Dataset Kaggle puis renseigne local_dir")
    imgs = [r for r in loose if Path(r["name"]).suffix.lower() in IMG_EXT]
    others = [r for r in loose if r not in imgs and r["size"] <= 5e6]
    rr = random.Random(SEED)
    rr.shuffle(imgs)
    chosen = imgs[:max_images]
    stems = {Path(r["name"]).stem for r in chosen}
    all_stems = {Path(r["name"]).stem for r in imgs}
    keep = [r for r in others if Path(r["name"]).suffix.lower() not in {".txt", ".xml"}
            or Path(r["name"]).stem in stems or Path(r["name"]).stem not in all_stems]
    todo = chosen + keep
    log(f"Dataverse : téléchargement de {len(todo)} fichiers individuels")

    def one(r):
        download_file(f"{DATAVERSE}/api/access/datafile/{r['id']}", safe_join(dest / r["dir"], r["name"]), r["size"])

    with ThreadPoolExecutor(N_THREADS) as ex:
        list(ex.map(one, todo))
    return dest


def fetch_mendeley(dataset_id, dest, max_images, version=1):
    url = f"https://data.mendeley.com/public-api/zip/{dataset_id}/download/{version}"
    try:
        zip_extract_subset(url, dest, max_images)
    except Exception as e:
        log("lecture à la demande impossible :", e, "→ téléchargement complet")
        tmp = download_file(url, RAW / "_zips" / f"mendeley_{dataset_id}.zip")
        zip_extract_subset(str(tmp), dest, max_images)
        tmp.unlink()
    return dest


def fetch_zip_url(url, dest, max_images):
    try:
        zip_extract_subset(url, dest, max_images)
    except Exception as e:
        log("lecture à la demande impossible :", e, "→ téléchargement complet")
        tmp = download_file(url, RAW / "_zips" / (re.sub(r"\W+", "_", url)[-60:] + ".zip"))
        zip_extract_subset(str(tmp), dest, max_images)
        tmp.unlink()
    return dest

# %%
# ===== 4. OBTENIR LES SOURCES =====
def count_files(p):
    return sum(1 for q in Path(p).rglob("*") if q.is_file())


def find_existing(name, cfg):
    if cfg.get("local_dir") and Path(cfg["local_dir"]).exists():
        return Path(cfg["local_dir"])
    if (RAW / name).exists() and count_files(RAW / name) > 0:
        return RAW / name
    if INPUT_ROOT.exists():
        key = name.lower().replace("_", "")
        for d in sorted(INPUT_ROOT.iterdir()):
            if key[:6] in d.name.lower().replace("-", "").replace("_", ""):
                return d
    return None


def prepare_sources():
    roots = {}
    for name, cfg in SOURCES.items():
        if not cfg["enabled"]:
            continue
        root = find_existing(name, cfg)
        if root is None and DOWNLOAD:
            dest = RAW / name
            log(f"=== téléchargement : {name} ===")
            try:
                if cfg.get("dataverse_doi"):
                    fetch_dataverse(cfg["dataverse_doi"], dest, cfg["max_images"])
                elif cfg.get("mendeley_id"):
                    fetch_mendeley(cfg["mendeley_id"], dest, cfg["max_images"])
                elif cfg.get("zip_url"):
                    fetch_zip_url(cfg["zip_url"], dest, cfg["max_images"])
                else:
                    log(f"{name} : pas d'adresse de téléchargement, renseigne local_dir.")
                unpack_nested(dest)
                root = dest if dest.exists() else None
            except Exception as e:
                log(f"ÉCHEC pour {name} : {type(e).__name__}: {e}")
                log("→ plan B : télécharge le jeu sur ton PC, ajoute-le comme Dataset Kaggle (Add Input), "
                    "puis relance (il sera trouvé dans /kaggle/input) ou renseigne SOURCES[...]['local_dir'].")
        if root is None:
            log(f"{name} : source ABSENTE (ignorée)")
        else:
            log(f"{name} : {root} ({count_files(root)} fichiers)")
            roots[name] = root
    return roots


ROOTS = prepare_sources()

# %%
# ===== 5. INVENTAIRE : que contiennent réellement les fichiers reçus ? =====
def inventory(name, root, n_head=2):
    root = Path(root)
    files = [p for p in root.rglob("*") if p.is_file()]
    ext = Counter(p.suffix.lower() for p in files)
    gb = sum(p.stat().st_size for p in files) / 1e9
    print(f"\n########## {name} : {len(files)} fichiers, {gb:.2f} Go ##########")
    print("extensions :", dict(ext.most_common(8)))
    dirs = Counter()
    for p in files:
        rel = p.relative_to(root).parts
        dirs["/".join(rel[:-1][:2]) or "(racine)"] += 1
    print("dossiers (2 niveaux) :")
    for d, n in dirs.most_common(12):
        print(f"   {n:6d}  {d}")
    for e in (".yaml", ".yml", ".json", ".csv", ".xml", ".txt"):
        sample = [p for p in files if p.suffix.lower() == e][:n_head]
        for p in sample:
            try:
                head = open(p, encoding="utf-8", errors="ignore").read(300).replace("\n", " | ")
            except Exception:
                head = "(illisible)"
            print(f"   [{e}] {p.relative_to(root)} -> {head}")


def inspect_cornell():
    if not CORNELL["enabled"]:
        return
    log("=== Cornell : inspection du zip distant ===")
    try:
        s = zip_summary(CORNELL["url"])
        print(json.dumps(s, indent=1, ensure_ascii=False))
        zip_extract_subset(CORNELL["url"], RAW / "cornell_sample", CORNELL["sample_images"])
        inventory("cornell_sample", RAW / "cornell_sample")
    except Exception as e:
        log("Cornell : échec", type(e).__name__, e)
        log("→ si le serveur refuse les requêtes Range, télécharge un sous-ensemble sur ton PC et ajoute-le comme Dataset Kaggle.")


for _n, _r in ROOTS.items():
    inventory(_n, _r)
inspect_cornell()
if not RUN_COMPLET:
    print("\n>>> Mode inventaire terminé. Lis les sorties ci-dessus, puis passe RUN_MODE à \"complet\" et relance tout.")

# %%
# ===== 6. CORRESPONDANCE DES CLASSES → SAIN / MALADE_OU_RAVAGEUR =====
M, S = "MALADE_OU_RAVAGEUR", "SAIN"
_L = r"(?<![a-z])"   # début de mot (le « _ » des noms de fichiers n'est pas un séparateur pour \b)
_R = r"(?![a-z])"
RULES = [  # (motif sur le nom en minuscules, étiquette fine, étiquette binaire) — le premier motif gagnant l'emporte
    (re.compile(r"none[ _\-]?health"), None, None),                                  # ambigu : quarantaine
    (re.compile(r"(?:un|non|not)[ _\-]?health"), "malade_non_precise", M),
    (re.compile(r"health|" + _L + r"sain" + _R + "|" + _L + r"normal"), "sain", S),
    (re.compile(r"streak|" + _L + r"msv" + _R), "striure_msv", M),
    (re.compile(r"northern|helmintho|blight|" + _L + r"(?:nlb|mlb)" + _R), "helminthosporiose", M),
    (re.compile(r"rust|rouille"), "rouille_commune", M),
    (re.compile(r"gr[ae]y|cercospor|" + _L + r"gls" + _R), "cercosporiose", M),
    (re.compile(r"armyworm|frass|larva|" + _L + r"egg|ravageur|" + _L + r"pest|" + _L + r"faw" + _R), "legionnaire_ravageur", M),
    (re.compile(r"diseas|malad"), "malade_non_precise", M),     # générique : en dernier (« maize streak disease » est plus précis)
]


def classify_name(s):
    s = str(s).lower()
    for rx, fine, binary in RULES:
        if rx.search(s):
            return fine, binary
    return None, None


def decide(names):
    """names : noms de classes d'une image → (étiquette fine, binaire, motif de rejet)."""
    mapped = [classify_name(n) if n else (None, None) for n in names]
    bins = [b for _, b in mapped if b]
    if M in bins:
        fines = [f for f, b in mapped if b == M]
        return "|".join(sorted(set(fines))), M, None
    if bins and len(bins) == len(mapped):
        return "sain", S, None
    bad = sorted({str(n) for n, (_, b) in zip(names, mapped) if not b})
    return None, None, "classe non reconnue : " + ",".join(bad) if names else "annotation vide"


def load_class_names(root):
    out = {}
    if yaml is not None:
        for y in list(Path(root).rglob("*.yaml")) + list(Path(root).rglob("*.yml")):
            try:
                d = yaml.safe_load(open(y, encoding="utf-8"))
            except Exception:
                continue
            if isinstance(d, dict) and "names" in d:
                n = d["names"]
                if isinstance(n, dict):
                    n = [n[k] for k in sorted(n, key=lambda x: int(x))]
                out[y.parent] = [str(x) for x in n]
    for t in Path(root).rglob("classes.txt"):
        out.setdefault(t.parent, [l.strip() for l in open(t, encoding="utf-8", errors="ignore") if l.strip()])
    return out


def names_for(img, names_by_dir):
    for p in img.parents:
        if p in names_by_dir:
            return names_by_dir[p]
    return next(iter(names_by_dir.values()), None)


def sidecar_candidates(img):
    c = [img.with_suffix(".txt"), img.with_suffix(".xml")]
    parts = list(img.parts)
    if "images" in parts:
        k = len(parts) - 1 - parts[::-1].index("images")
        c.insert(0, Path(*parts[:k], "labels", *parts[k + 1:]).with_suffix(".txt"))
    return c


def read_sidecar(img, names_by_dir):
    """→ (type, liste de boîtes {name,cx,cy,w,h}) ou (None, None). Boîtes normalisées (0-1)."""
    for c in sidecar_candidates(img):
        if not c.exists():
            continue
        boxes = []
        if c.suffix == ".txt":
            names = names_for(img, names_by_dir) if names_by_dir else None
            for line in open(c, encoding="utf-8", errors="ignore"):
                t = line.split()
                if len(t) < 5:
                    continue
                try:
                    cid = int(float(t[0]))
                    v = [float(x) for x in t[1:]]
                except ValueError:
                    continue
                if len(v) == 4:
                    cx, cy, w, h = v
                else:                                    # polygone → boîte englobante
                    xs, ys = v[0::2], v[1::2]
                    cx, cy, w, h = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs), max(ys) - min(ys)
                nm = names[cid] if names and 0 <= cid < len(names) else None
                boxes.append(dict(name=nm, cid=cid, cx=cx, cy=cy, w=w, h=h))
            return "yolo", boxes
        try:
            root = ET.parse(c).getroot()
            W = float(root.findtext("size/width") or 0)
            H = float(root.findtext("size/height") or 0)
            if not W or not H:
                with Image.open(img) as im:
                    W, H = im.size
            for o in root.iter("object"):
                bb = o.find("bndbox")
                if bb is None:
                    continue
                x1, y1, x2, y2 = (float(bb.findtext(k)) for k in ("xmin", "ymin", "xmax", "ymax"))
                boxes.append(dict(name=o.findtext("name"), cid=None, cx=(x1 + x2) / 2 / W, cy=(y1 + y2) / 2 / H,
                                  w=(x2 - x1) / W, h=(y2 - y1) / H))
            return "voc", boxes
        except Exception:
            continue
    return None, None


def folder_cue(img, root):
    rel = img.relative_to(root)
    for part in list(rel.parts[:-1])[::-1] + [rel.stem]:
        fine, binary = classify_name(part)
        if binary:
            return fine, binary
    return None, None

# %%
# ===== 7. LISTE DES IMAGES (manifeste brut) =====
def origin_key(img):
    """Clé de regroupement pour éviter les fuites : copies augmentées Roboflow, séances de collecte, date EXIF."""
    stem = img.stem
    m = re.match(r"^(.+?)_(?:jpg|jpeg|png)\.rf\.[0-9a-f]+$", stem)
    base = m.group(1) if m else stem
    if re.fullmatch(r"1[5-8]\d{11}", base):               # horodatage en millisecondes : seau d'environ 2,8 h
        return "ts" + base[:6]
    try:
        with Image.open(img) as im:
            dt = im.getexif().get(306)
        if dt:
            return "exif" + str(dt)[:13]                  # AAAA:MM:JJ HH
    except Exception:
        pass
    return "f" + base


def scan_source(name, cfg, root):
    root = Path(root)
    names_by_dir = load_class_names(root)
    filt = re.compile(cfg["class_filter"], re.I) if cfg.get("class_filter") else None
    rows = []
    for p in sorted(root.rglob("*")):
        if not (p.is_file() and p.suffix.lower() in IMG_EXT):
            continue
        rec = dict(source=name, domain=cfg["domain"], train_only=bool(cfg["train_only"]), path=str(p),
                   rel=str(p.relative_to(root)), label_origin="aucun", fine=None, binary=None, reason=None,
                   boxes_json=None, origin=name + ":" + origin_key(p))
        kind, boxes = read_sidecar(p, names_by_dir)
        if kind is not None:
            rec["label_origin"] = kind
            if filt is not None:
                boxes = [b for b in boxes if b["name"] and filt.search(b["name"])]
                if not boxes:
                    rec["reason"] = "hors maïs (filtre de classes)"
                    rows.append(rec)
                    continue
            fine, binary, why = decide([b["name"] for b in boxes])
            rec.update(fine=fine, binary=binary, reason=why, boxes_json=json.dumps(boxes))
        else:
            if filt is not None and not filt.search(rec["rel"]):
                rec["reason"] = "hors maïs (filtre de classes)"
                rows.append(rec)
                continue
            fine, binary = folder_cue(p, root)
            if binary:
                rec.update(label_origin="dossier", fine=fine, binary=binary)
            else:
                rec["reason"] = "aucune étiquette (ni annotation ni nom de dossier reconnu)"
        rows.append(rec)
    return rows

# %%
# ===== 8. VALIDATION DES IMAGES + EMPREINTES (doublons) =====
def file_md5(path, max_mb=60):
    if os.path.getsize(path) > max_mb * 1e6:
        return None
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_info(path):
    """Taille, md5 et 8 empreintes dHash 64 bits (une par rotation/miroir : les copies tournées sont des doublons)."""
    try:
        with Image.open(path) as im:
            w, h = im.size
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
        return dict(ok=True, width=w, height=h, md5=file_md5(path), hashes=hs)
    except Exception as e:
        return dict(ok=False, error=f"{type(e).__name__}")


def cluster_duplicates(H, T):
    """H : liste de 8 empreintes par image. Union-find sur les paires à distance <= T (recherche par morceaux de bits :
    si <= T bits diffèrent, au moins un des T+1 morceaux est identique)."""
    n = len(H)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

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
        seen = set()
        for c in range(nch):
            lo, hi = bounds[c], bounds[c + 1]
            lst = buckets[c].get((h0 >> lo) & ((1 << (hi - lo)) - 1), ())
            if len(lst) > 4000:
                skipped += 1
                continue
            for j, k in lst:
                if j <= i or j in seen:
                    continue
                if bin(h0 ^ H[j][k]).count("1") <= T:
                    seen.add(j)
                    union(i, j)
    if skipped:
        log(f"(attention : {skipped} paquets d'empreintes trop gros ignorés — images peu texturées)")
    return [find(i) for i in range(n)]

# %%
# ===== 9. SÉLECTION, DÉDOUBLONNAGE, DÉCOUPAGE SANS FUITE =====
def build_manifest(roots):
    rows = []
    for name, root in roots.items():
        r = scan_source(name, SOURCES[name], root)
        log(f"{name} : {len(r)} images trouvées")
        rows += r
    return pd.DataFrame(rows)


def validate_and_dedupe(df):
    log("validation des images et empreintes ...")
    with ThreadPoolExecutor(N_THREADS) as ex:
        infos = list(ex.map(image_info, df["path"].tolist()))
    df = df.copy()
    df["ok"] = [i["ok"] for i in infos]
    df["width"] = [i.get("width") for i in infos]
    df["height"] = [i.get("height") for i in infos]
    df["md5"] = [i.get("md5") for i in infos]
    hashes = [i.get("hashes") for i in infos]
    bad = ~df["ok"]
    df.loc[bad, "reason"] = "image illisible"
    small = df["ok"] & ((df["width"] < MIN_SIDE) | (df["height"] < MIN_SIDE))
    df.loc[small, "reason"] = f"trop petite (< {MIN_SIDE} px)"
    cand = df.index[df["ok"] & df["reason"].isna()].tolist()
    # 1) doublons exacts (md5) + 2) quasi-doublons (empreintes)
    idx = {k: n for n, k in enumerate(cand)}
    cl = cluster_duplicates([hashes[k] for k in cand], DUP_HAMMING)
    parent = list(range(len(cand)))
    root_of = {}
    for n, c in enumerate(cl):
        root_of.setdefault(c, n)
        parent[n] = root_of[c]
    md5_first = {}
    for n, k in enumerate(cand):
        m = df.at[k, "md5"]
        if m:
            if m in md5_first:
                parent[n] = parent[md5_first[m]]
            else:
                md5_first[m] = n
    df["dup_cluster"] = -1
    for n, k in enumerate(cand):
        df.at[k, "dup_cluster"] = parent[n]
    return df


def resolve_clusters(df):
    """Conflits d'étiquette (même image dans deux classes) → quarantaine ; sinon on garde un représentant par grappe."""
    df = df.copy()
    ok = df[df["reason"].isna() & df["binary"].notna() & (df["dup_cluster"] >= 0)]
    conflicts = 0
    for cid, g in ok.groupby("dup_cluster"):
        if g["binary"].nunique() > 1:
            df.loc[g.index, "reason"] = "conflit d'étiquettes entre doublons"
            conflicts += len(g)
    ok = df[df["reason"].isna() & df["binary"].notna()]
    ok = ok.assign(pix=ok["width"] * ok["height"], pref=(~ok["train_only"]).astype(int))
    keep = ok.sort_values(["pref", "pix"], ascending=False).groupby("dup_cluster").head(1).index
    dropped = ok.index.difference(keep)
    df.loc[dropped, "reason"] = "doublon (copie écartée)"
    log(f"doublons écartés : {len(dropped)} ; images en conflit d'étiquettes : {conflicts}")
    return df


def apply_caps(df):
    df = df.copy()
    ok = df[df["reason"].isna() & df["binary"].notna()]
    r = random.Random(SEED)
    for (s, b), g in ok.groupby(["source", "binary"]):
        if len(g) > MAX_PER_CLASS_PER_SOURCE:
            drop = r.sample(list(g.index), len(g) - MAX_PER_CLASS_PER_SOURCE)
            df.loc[drop, "reason"] = "au-delà du plafond par classe"
    return df


def assign_splits(df):
    """Découpage par GROUPES (jamais une même origine dans deux ensembles), stratifié par (source, classe)."""
    df = df.copy()
    df["split"] = None
    ok = df["reason"].isna() & df["binary"].notna()
    d = df[ok].copy()
    d["stratum"] = d["source"] + "|" + d["binary"]
    d["group"] = d["origin"]
    tgt = dict(train=SPLIT[0], val=SPLIT[1], test=SPLIT[2])
    g = d.groupby("group").agg(n=("path", "size"), stratum=("stratum", lambda s: s.value_counts().index[0]),
                               train_only=("train_only", "max"))
    gsplit = {}
    for k in g.index[g["train_only"]]:
        gsplit[k] = "train"
    r = random.Random(SEED)
    for stratum, sub in g[~g["train_only"]].groupby("stratum"):
        ns = sub["n"].to_dict()
        total = sum(ns.values())
        acc = dict(train=0, val=0, test=0)
        for k in sorted(ns, key=lambda x: (-ns[x], r.random())):
            deficits = {s: tgt[s] * total - acc[s] for s in acc}
            best = max(deficits, key=deficits.get)
            gsplit[k] = best
            acc[best] += ns[k]
    d["split"] = d["group"].map(gsplit)
    df.loc[d.index, "split"] = d["split"]
    df.loc[d.index, "group"] = d["group"]
    return df


def check_no_leak(df):
    d = df[df["split"].notna()]
    g = d.groupby("group")["split"].nunique()
    assert (g <= 1).all(), "FUITE : un groupe apparaît dans plusieurs ensembles"
    c = d[d["dup_cluster"] >= 0].groupby("dup_cluster")["split"].nunique()
    assert (c <= 1).all(), "FUITE : des doublons sont dans plusieurs ensembles"
    m = d[d["md5"].notna()].groupby("md5")["split"].nunique()
    assert (m <= 1).all(), "FUITE : fichiers identiques dans plusieurs ensembles"
    assert not d[(d["train_only"]) & (d["split"] != "train")].shape[0], "FUITE : source train_only hors train"
    log("contrôle anti-fuite : OK (groupes, doublons, fichiers identiques)")

# %%
# ===== 10. EXPORT (classification + détection) =====
def letterbox(im, size):
    w, h = im.size
    s = size / max(w, h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas.paste(im.resize((nw, nh), Image.LANCZOS), (px, py))
    return canvas, s, px, py


def transform_box(b, W, H, s, px, py, size):
    x1, y1 = (b["cx"] - b["w"] / 2) * W * s + px, (b["cy"] - b["h"] / 2) * H * s + py
    x2, y2 = (b["cx"] + b["w"] / 2) * W * s + px, (b["cy"] + b["h"] / 2) * H * s + py
    x1, y1, x2, y2 = (min(max(v, 0), size) for v in (x1, y1, x2, y2))
    if x2 - x1 < 1 or y2 - y1 < 1:
        return None
    return ((x1 + x2) / 2 / size, (y1 + y2) / 2 / size, (x2 - x1) / size, (y2 - y1) / size)


def export_one(rec):
    p = Path(rec["path"])
    key = hashlib.md5(rec["rel"].encode()).hexdigest()[:8]
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", p.stem)[:60]
    name = f"{rec['source']}__{stem}__{key}.jpg"
    out = WORK / "cls" / rec["split"] / rec["binary"] / name
    has_boxes = bool(rec["boxes_json"])
    with Image.open(p) as im:
        im = im if has_boxes else ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        W, H = im.size
        lb, s, px, py = letterbox(im, IMG_SIZE)
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        lb.save(out, "JPEG", quality=92)
    return dict(out_path=str(out.relative_to(WORK)), scale=s, pad_x=px, pad_y=py, orig_w=W, orig_h=H)


def export_classification(df):
    d = df[df["split"].notna()]
    recs = d.to_dict("records")
    log(f"export classification : {len(recs)} images ...")
    with ThreadPoolExecutor(N_THREADS) as ex:
        res = list(ex.map(export_one, recs))
    for k in ("out_path", "scale", "pad_x", "pad_y", "orig_w", "orig_h"):
        df.loc[d.index, k] = [r[k] for r in res]
    return df


def export_detection(df, pseudo_area=0.9):
    """Boîtes → une seule classe « malade_ou_ravageur » (id 0). Les boîtes qui couvrent presque toute l'image
    (étiquettes d'image déguisées, p. ex. Makerere) sont ignorées. Images sans boîte malade mais avec boîtes
    « sain » → arrière-plan (fichier vide)."""
    d = df[df["split"].notna() & df["boxes_json"].notna()]
    n_img = n_box = 0
    for rec in d.to_dict("records"):
        boxes = json.loads(rec["boxes_json"])
        real = [b for b in boxes if b["w"] * b["h"] < pseudo_area]
        if not real:
            continue
        mal = [b for b in real if classify_name(b["name"] or "")[1] == M]
        lines = []
        for b in mal:
            t = transform_box(b, rec["orig_w"], rec["orig_h"], rec["scale"], rec["pad_x"], rec["pad_y"], IMG_SIZE)
            if t:
                lines.append("0 " + " ".join(f"{v:.6f}" for v in t))
        if not mal and rec["binary"] != S:
            continue
        src = WORK / rec["out_path"]
        name = Path(rec["out_path"]).name
        di = WORK / "det" / rec["split"] / "images"
        dl = WORK / "det" / rec["split"] / "labels"
        di.mkdir(parents=True, exist_ok=True)
        dl.mkdir(parents=True, exist_ok=True)
        dst = di / name
        if not dst.exists():
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
        (dl / (Path(name).stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
        n_img += 1
        n_box += len(lines)
    (WORK / "det").mkdir(exist_ok=True)
    (WORK / "det" / "dataset.yaml").write_text(
        "path: " + str(WORK / "det") + "\ntrain: train/images\nval: val/images\ntest: test/images\nnames:\n  0: malade_ou_ravageur\n")
    log(f"export détection : {n_img} images, {n_box} boîtes")


def visual_check(df, n=10):
    """Planche de contrôle visuel : quelques images de classification et des boîtes de détection superposées."""
    qc = WORK / "qc"
    qc.mkdir(exist_ok=True)
    d = df[df["split"].notna()]
    r = random.Random(SEED)
    for (b, sp), g in d.groupby(["binary", "split"]):
        pick = g.sample(min(4, len(g)), random_state=SEED)
        tiles = [Image.open(WORK / p).resize((256, 256)) for p in pick["out_path"]]
        sheet = Image.new("RGB", (256 * max(1, len(tiles)), 256))
        for i, t in enumerate(tiles):
            sheet.paste(t, (256 * i, 0))
        sheet.save(qc / f"cls_{b}_{sp}.jpg", quality=85)
    for sp in ("train", "val", "test"):
        li = sorted((WORK / "det" / sp / "labels").glob("*.txt"))[:n] if (WORK / "det" / sp / "labels").exists() else []
        for lf in li:
            im = Image.open(WORK / "det" / sp / "images" / (lf.stem + ".jpg")).convert("RGB")
            dr = ImageDraw.Draw(im)
            for line in lf.read_text().split("\n"):
                if line.strip():
                    _, cx, cy, w, h = map(float, line.split())
                    dr.rectangle([(cx - w / 2) * IMG_SIZE, (cy - h / 2) * IMG_SIZE, (cx + w / 2) * IMG_SIZE, (cy + h / 2) * IMG_SIZE],
                                 outline=(255, 0, 0), width=2)
            im.save(qc / f"det_{sp}_{lf.stem[:40]}.jpg", quality=85)
    log("planches de contrôle écrites dans", qc)

# %%
# ===== 11. LANCEMENT DU TRAITEMENT COMPLET + RAPPORTS =====
def run_pipeline():
    df = build_manifest(ROOTS)
    df = validate_and_dedupe(df)
    df = resolve_clusters(df)
    df = apply_caps(df)
    df = assign_splits(df)
    check_no_leak(df)
    df = export_classification(df)
    export_detection(df)
    visual_check(df)
    keep_cols = [c for c in df.columns if c != "boxes_json"]
    df[keep_cols + ["boxes_json"]].to_csv(WORK / "manifest.csv", index=False)
    q = df[df["split"].isna()]
    q[["source", "rel", "label_origin", "reason"]].to_csv(WORK / "quarantaine.csv", index=False)
    used = df[df["split"].notna()]
    tab = used.groupby(["source", "split", "binary"]).size().unstack("binary", fill_value=0)
    tab.to_csv(WORK / "effectifs.csv")
    print("\n===== EFFECTIFS (images) par source / ensemble / classe =====")
    print(tab.to_string())
    print("\n===== MAPPING des classes d'origine (étiquette fine → binaire) =====")
    print(used.groupby(["source", "fine", "binary"]).size().to_string())
    print("\n===== QUARANTAINE / REJETS (motif) =====")
    print(q.groupby(["source", "reason"], dropna=False).size().to_string())
    gs = used.groupby("group").size()
    print(f"\ngroupes : {len(gs)} ; plus gros groupe : {gs.max()} images ({gs.max() / len(used):.1%} du total)")
    dom = used.groupby(["split", "domain"]).size().unstack(fill_value=0)
    print("\n===== DOMAINES par ensemble (aucune image de drone en v1 : attendu) =====")
    print(dom.to_string())
    (WORK / "README_dataset.md").write_text(
        "# Jeu de données maïs — préparé par 01_preparation_donnees\n\n"
        f"- SEED={SEED}, IMG_SIZE={IMG_SIZE}, MIN_SIDE={MIN_SIDE}, DUP_HAMMING={DUP_HAMMING}, SPLIT={SPLIT}\n"
        "- `cls/{train,val,test}/{SAIN,MALADE_OU_RAVAGEUR}/` : classification (image carrée, bandes grises)\n"
        "- `det/` : détection YOLO, une classe (0 = malade_ou_ravageur), `det/dataset.yaml`\n"
        "- `manifest.csv` : une ligne par image (source, étiquette fine, ensemble, groupe, empreintes)\n"
        "- `quarantaine.csv` : images écartées et motif\n"
        "- Sources et licences : voir SOURCES.csv du projet (CC0 / CC BY 4.0 : citer les auteurs)\n")
    return df


if RUN_COMPLET:
    MANIFEST = run_pipeline()
    log("Terminé. Résultats dans", WORK)
else:
    log("RUN_COMPLET=False : traitement non lancé (mode inventaire).")

# %%
# ===== 12. OUTILS DRONE (pour la suite) : tuilage et résolution au sol =====
def gsd_cm(altitude_m, sensor_w_mm, focal_mm, img_w_px):
    """Résolution au sol (cm/pixel) = altitude × largeur capteur × 100 / (focale × largeur image)."""
    return altitude_m * sensor_w_mm * 100 / (focal_mm * img_w_px)


def iter_tiles(w, h, tile=512, stride=512):
    """Positions (x0, y0, x1, y1) de tuiles couvrant toute l'image (la dernière colonne/ligne est recalée au bord)."""
    xs = list(range(0, max(w - tile, 0) + 1, stride))
    ys = list(range(0, max(h - tile, 0) + 1, stride))
    if xs[-1] + tile < w:
        xs.append(w - tile)
    if ys[-1] + tile < h:
        ys.append(h - tile)
    for y in ys:
        for x in xs:
            yield (x, y, min(x + tile, w), min(y + tile, h))


# Le marquage des tuiles Cornell (positif = une lésion annotée dans la tuile) sera ajouté APRÈS lecture
# de l'inventaire (format des annotations à vérifier). Voir le message de livraison.
