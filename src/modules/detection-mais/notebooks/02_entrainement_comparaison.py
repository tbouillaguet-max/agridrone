# %% [markdown]
# # Livrable 3 — Entraînement et comparaison des modèles (maïs : SAIN / MALADE_OU_RAVAGEUR)
#
# **Entrée** : la sortie du notebook `01_preparation_donnees` (dossier `maize_prep/` avec `cls/`, `det/`, `manifest.csv`).
# Sur Kaggle : panneau de droite → *Add Input* → *Notebooks* → choisir ton notebook 01 (version « complet »).
#
# **Réglages Kaggle** : Accelerator = **GPU T4 x2** (n'utilise qu'un GPU ; éviter le P100, mal pris en charge par les
# versions récentes de PyTorch), Internet = **On** (installation d'Ultralytics + poids pré-entraînés).
#
# **Modèles comparés** (tous entraînés sur les mêmes ensembles train/val, jugés sur le même test) :
#
# | nom | famille | tâche | pourquoi |
# |---|---|---|---|
# | `effnet_b0` | EfficientNet-B0 (timm) | classification de tuile | référence légère solide |
# | `mnv3_large` | MobileNetV3-Large (timm) | classification de tuile | le plus rapide sur CPU |
# | `yolo26n_cls` | YOLO26 nano (Ultralytics) | classification de tuile | YOLO imposé, version classif |
# | `yolo26n_det` / `yolo26s_det` | YOLO26 nano / small | détection (boîtes) | YOLO imposé ; localise les lésions |
# | `dinov2s_lin` | DINOv2-small gelé + tête linéaire | classification de tuile | caractéristiques auto-supervisées, robustes au changement de domaine |
# | `rtdetr_l` | RT-DETR-L (désactivé) | détection | demandé « si les boîtes le permettent » ; trop lourd pour le CPU |
#
# **Méthode** : chaque modèle produit un *score* « malade » par image. Le seuil est choisi **sur la validation** pour
# atteindre un rappel cible sur MALADE (par défaut 95 %), puis appliqué tel quel au test. Le choix du modèle se fait
# **sur la validation uniquement** (le test sert seulement à rapporter le résultat final).
#
# **Deux passes** :
# 1. `MODE = "test_rapide"` : quelques images, 1 époque par modèle (~10–15 min). Vérifie que tout tourne.
# 2. `MODE = "complet"` : entraînement réel. Lance-le avec **Save Version → Save & Run All (Commit)** : il tourne en
#    arrière-plan jusqu'à 12 h, même navigateur fermé, et les résultats sont gardés dans l'onglet *Output*.
#
# **Reprise** : chaque modèle écrit un point de reprise à chaque époque. Si la session s'arrête, ajoute la sortie de
# ce notebook comme *Input* et relance : les modèles terminés sont sautés, les autres reprennent où ils en étaient.

# %%
# ===== 1. PARAMÈTRES (c'est la seule cellule à modifier) =====
from pathlib import Path

MODE = "test_rapide"          # "test_rapide" puis "complet"
SEED = 42
IMG_SIZE = 512                # taille des tuiles (identique au notebook 01)
RECALL_TARGET = 0.95          # rappel visé sur MALADE_OU_RAVAGEUR (seuil choisi sur la validation)
SESSION_HOURS = 11.0          # on s'arrête proprement avant la limite Kaggle de 12 h
RESUME = True                 # reprendre les entraînements interrompus / sauter les modèles terminés
PRETRAINED = True             # poids pré-entraînés (ImageNet / COCO / LVD-142M) ; False seulement pour des tests hors ligne
DATA_DIR = None               # None = recherche automatique de maize_prep/ dans /kaggle/input puis /kaggle/working

# Modèles : enabled=False pour en sauter un. max_hours = budget par modèle (en plus du budget de session).
MODELS = {
    "effnet_b0":   dict(enabled=True,  kind="timm",     arch="efficientnet_b0.ra_in1k",
                        epochs=25, batch=48, lr=4e-4, max_hours=1.6),
    "mnv3_large":  dict(enabled=True,  kind="timm",     arch="mobilenetv3_large_100.ra_in1k",
                        epochs=25, batch=64, lr=6e-4, max_hours=1.3),
    "yolo26n_cls": dict(enabled=True,  kind="yolo_cls", weights="yolo26n-cls.pt",
                        epochs=30, batch=64, max_hours=1.3),
    "yolo26n_det": dict(enabled=True,  kind="yolo_det", weights="yolo26n.pt",
                        epochs=80, batch=32, max_hours=2.0),
    "yolo26s_det": dict(enabled=True,  kind="yolo_det", weights="yolo26s.pt",
                        epochs=80, batch=24, max_hours=2.6),
    "dinov2s_lin": dict(enabled=True,  kind="dino_lin", arch="vit_small_patch14_dinov2.lvd142m",
                        img=448, batch=64, max_hours=0.6),
    "rtdetr_l":    dict(enabled=False, kind="yolo_det", weights="rtdetr-l.pt",
                        epochs=50, batch=8, max_hours=3.0),
}

ON_KAGGLE = Path("/kaggle").exists()
OUT = Path("/kaggle/working/train") if ON_KAGGLE else Path("./train_out")
INPUT_ROOT = Path("/kaggle/input")
ULTRALYTICS_VERSION = "8.4.183"   # version testée ; Ultralytics est sous licence AGPL-3.0 (modèles entraînés compris)
TIMM_VERSION = "1.0.30"

# %%
# ===== 2. INSTALLATION + OUTILS =====
import importlib, subprocess, sys


def ensure(pkg, version):
    """Installe la version demandée si le module manque ou n'est pas à la bonne version."""
    name = pkg.split("[")[0]
    try:
        m = importlib.import_module(name)
        if getattr(m, "__version__", None) == version:
            return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", f"{pkg}=={version}"], check=True)


if ON_KAGGLE:
    ensure("ultralytics", ULTRALYTICS_VERSION)
    ensure("timm", TIMM_VERSION)

import json, math, os, random, shutil, time, warnings
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from PIL import Image
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve

warnings.filterwarnings("ignore", category=UserWarning)
T0 = time.time()
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
N_WORKERS = min(8, os.cpu_count() or 2)
POS, NEG = "MALADE_OU_RAVAGEUR", "SAIN"
QUICK = MODE == "test_rapide"
RUNS, RES, EXPORT = OUT / "runs", OUT / "resultats", OUT / "export"
for d in (RUNS, RES, EXPORT, RES / "preds"):
    d.mkdir(parents=True, exist_ok=True)


def log(*a):
    print(f"[{(time.time() - T0) / 60:6.1f} min]", *a, flush=True)


def hours_left():
    return SESSION_HOURS - (time.time() - T0) / 3600


def seed_all(s=SEED):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


seed_all()
torch.backends.cudnn.benchmark = True
log(f"MODE={MODE} | appareil={DEVICE} | "
    + (torch.cuda.get_device_name(0) if DEVICE == "cuda" else "pas de GPU (normal en test local, lent sur Kaggle)"))
if MODE == "complet" and DEVICE != "cuda":
    log("ATTENTION : mode complet sans GPU. Active Accelerator = GPU T4 x2 dans les réglages.")

# %%
# ===== 3. DONNÉES : localisation, table des images, contrôles =====
def _walk_find(root, name="maize_prep", max_depth=5):
    root = Path(root)
    if not root.exists():
        return []
    found = []
    base = len(root.parts)
    for dp, dn, _ in os.walk(root):
        if len(Path(dp).parts) - base >= max_depth:
            dn[:] = []
        if Path(dp).name == name and (Path(dp) / "cls").is_dir():
            found.append(Path(dp))
            dn[:] = []
    return found


def restore_previous():
    """Reprise inter-sessions : si la sortie d'une version précédente de CE notebook est attachée en Input
    (dossier train/ avec runs/), on la recopie dans /kaggle/working/train avant de continuer."""
    if not (RESUME and ON_KAGGLE and INPUT_ROOT.exists()):
        return
    if (RES / "modeles_termines.json").exists() or any(RUNS.iterdir()):
        return
    cands, base = [], len(INPUT_ROOT.parts)
    for dp, dn, _ in os.walk(INPUT_ROOT):
        p = Path(dp)
        if len(p.parts) - base >= 6 or p.name in ("cls", "det", "images", "labels"):
            dn[:] = []          # on ne descend pas dans les dossiers d'images
        elif p.name == "train" and (p / "runs").is_dir():
            cands.append(p); dn[:] = []
    if cands:
        src = max(cands, key=lambda p: (p / "resultats").stat().st_mtime if (p / "resultats").exists() else 0)
        log("reprise : copie de la session précédente depuis", src)
        shutil.copytree(src, OUT, dirs_exist_ok=True)


def find_data():
    cands = [Path(DATA_DIR)] if DATA_DIR else []
    cands += _walk_find(INPUT_ROOT) + _walk_find("/kaggle/working") + _walk_find(".", max_depth=3)
    for c in cands:
        if (c / "cls" / "train").is_dir():
            return c
    raise FileNotFoundError("maize_prep/ introuvable : ajoute la sortie du notebook 01 en Input (ou renseigne DATA_DIR).")


def build_table(data):
    """Une ligne par image exportée : chemin, ensemble, étiquette (1 = malade), source, étiquette fine, groupe."""
    rows = []
    for sp in ("train", "val", "test"):
        for cl in (NEG, POS):
            for p in sorted((data / "cls" / sp / cl).glob("*.jpg")):
                rows.append(dict(path=str(p), rel=f"cls/{sp}/{cl}/{p.name}", split=sp, y=int(cl == POS),
                                 source=p.name.split("__")[0]))
    df = pd.DataFrame(rows)
    man = data / "manifest.csv"
    if man.exists():
        m = pd.read_csv(man, usecols=lambda c: c in {"out_path", "fine", "group", "domain", "source"})
        m = m.dropna(subset=["out_path"]).drop_duplicates("out_path").rename(columns={"out_path": "rel"})
        df = df.merge(m.drop(columns=["source"], errors="ignore"), on="rel", how="left")
    for c in ("fine", "group", "domain"):
        if c not in df:
            df[c] = None
    df["fine"] = df["fine"].fillna(pd.Series(np.where(df["y"] == 1, "malade_non_precise", "sain"), index=df.index))
    df["group"] = df["group"].fillna(df["rel"])
    return df


def subsample(df, n_per=24):
    """Mode test rapide : quelques images par (ensemble, classe)."""
    return df.sample(frac=1, random_state=SEED).groupby(["split", "y"]).head(n_per).reset_index(drop=True)


restore_previous()
DATA = find_data()
TABLE = build_table(DATA)
assert len(TABLE), "aucune image dans cls/"
# Contrôle anti-fuite (redondant avec le notebook 01, mais gratuit) : un groupe ne doit apparaître que dans un ensemble.
_g = TABLE.groupby("group")["split"].nunique()
assert (_g <= 1).all(), "FUITE : un même groupe dans plusieurs ensembles"
if QUICK:
    TABLE = subsample(TABLE)
log("données :", DATA)
print(TABLE.groupby(["split", "source", "y"]).size().unstack("y", fill_value=0).rename(columns={0: NEG, 1: POS}).to_string())
DET_YAML = None
if (DATA / "det" / "train" / "images").is_dir() and any((DATA / "det" / "train" / "images").iterdir()):
    # Le dataset.yaml du notebook 01 contient un chemin absolu propre à SA session : on le réécrit.
    DET_YAML = OUT / "det_dataset.yaml"
    DET_YAML.write_text(f"path: {DATA / 'det'}\ntrain: train/images\nval: val/images\n"
                        + ("test: test/images\n" if (DATA / "det" / "test" / "images").is_dir() else "")
                        + "names:\n  0: malade_ou_ravageur\n")
else:
    log("pas de jeu de détection : les modèles YOLO de détection seront sautés")

# %%
# ===== 4. MÉTRIQUES (communes à tous les modèles) =====
def choose_threshold(y, s, target=RECALL_TARGET):
    """Plus grand seuil qui garde un rappel >= cible (donc la meilleure précision à ce rappel)."""
    y, s = np.asarray(y), np.asarray(s)
    if y.sum() == 0:
        return 0.5
    order = np.sort(np.unique(s))[::-1]
    for t in order:
        if ((s >= t) & (y == 1)).sum() / y.sum() >= target:
            return float(t)
    return float(order[-1])


def metrics_at(y, s, t):
    y, p = np.asarray(y), (np.asarray(s) >= t).astype(int)
    tp = int(((p == 1) & (y == 1)).sum()); fp = int(((p == 1) & (y == 0)).sum())
    fn = int(((p == 0) & (y == 1)).sum()); tn = int(((p == 0) & (y == 0)).sum())
    rec = tp / (tp + fn) if tp + fn else float("nan")
    pre = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * pre * rec / (pre + rec) if pre + rec else float("nan")
    f2 = 5 * pre * rec / (4 * pre + rec) if pre + rec else float("nan")
    spe = tn / (tn + fp) if tn + fp else float("nan")
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, recall=rec, precision=pre, f1=f1, f2=f2, specificity=spe)


def safe_auc(fn, y, s):
    try:
        return float(fn(y, s)) if len(set(y)) == 2 else float("nan")
    except ValueError:
        return float("nan")


def group_bootstrap(df, t, n=500, seed=SEED):
    """Intervalle à 95 % du rappel et de la précision, en rééchantillonnant des GROUPES (images corrélées)."""
    r = np.random.default_rng(seed)
    groups = df["group"].unique()
    by_g = {g: i for g, i in df.groupby("group").indices.items()}
    rec, pre = [], []
    for _ in range(n):
        idx = np.concatenate([by_g[g] for g in r.choice(groups, len(groups))])
        m = metrics_at(df["y"].values[idx], df["score"].values[idx], t)
        rec.append(m["recall"]); pre.append(m["precision"])
    q = lambda v: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5)))
    return q(rec), q(pre)


# %%
# ===== 5. CLASSIFIEURS timm (EfficientNet-B0, MobileNetV3) : données, augmentations, boucle d'entraînement =====
import timm
from torchvision.transforms import v2 as T


class RandomDownscale:
    """Réduit puis ré-agrandit l'image : simule une résolution au sol plus grossière (drone plus haut)."""
    def __init__(self, p=0.3, lo=0.35, hi=0.8):
        self.p, self.lo, self.hi = p, lo, hi

    def __call__(self, im):
        if random.random() > self.p:
            return im
        w, h = im.size
        f = random.uniform(self.lo, self.hi)
        return im.resize((max(8, int(w * f)), max(8, int(h * f))), Image.BILINEAR).resize((w, h), Image.BILINEAR)


def make_tf(img, mean, std, train):
    norm = [T.ToImage(), T.ToDtype(torch.float32, scale=True), T.Normalize(mean, std)]
    if not train:
        return T.Compose([T.Resize((img, img), antialias=True)] + norm)
    return T.Compose([
        RandomDownscale(),
        T.RandomResizedCrop(img, scale=(0.5, 1.0), ratio=(0.8, 1.25), antialias=True),
        T.RandomHorizontalFlip(), T.RandomVerticalFlip(),                   # vue du dessus : pas de « haut »
        T.RandomApply([T.RandomRotation((90, 90))], p=0.5),
        T.ColorJitter(0.3, 0.3, 0.25, 0.03),                                # éclairage / balance des blancs
        T.RandomApply([T.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.2),        # flou de mouvement / mise au point
    ] + norm)


class TileDS(Dataset):
    def __init__(self, df, tf):
        self.p, self.y, self.tf = df["path"].tolist(), df["y"].tolist(), tf

    def __len__(self):
        return len(self.p)

    def __getitem__(self, i):
        with Image.open(self.p[i]) as im:
            return self.tf(im.convert("RGB")), self.y[i]


def loader(df, tf, batch, shuffle):
    return DataLoader(TileDS(df, tf), batch_size=batch, shuffle=shuffle, num_workers=N_WORKERS,
                      pin_memory=DEVICE == "cuda", drop_last=shuffle and len(df) > batch,
                      persistent_workers=N_WORKERS > 0)


@torch.no_grad()
def predict_torch(model, df, tf, batch=64):
    """Probabilité « malade » (classe 1) pour chaque image de df."""
    model.eval()
    out = []
    for x, _ in loader(df, tf, batch, False):
        with torch.autocast(device_type="cuda", enabled=DEVICE == "cuda"):
            logits = model(x.to(DEVICE, non_blocking=True))
        out.append(torch.softmax(logits.float(), 1)[:, 1].cpu())
    return torch.cat(out).numpy() if out else np.array([])


def train_timm(name, cfg, tab):
    run = RUNS / name
    run.mkdir(parents=True, exist_ok=True)
    model = timm.create_model(cfg["arch"], pretrained=PRETRAINED, num_classes=2, drop_rate=0.2)
    dc = timm.data.resolve_model_data_config(model)
    mean, std = dc["mean"], dc["std"]
    model.to(DEVICE)
    tr, va = tab[tab.split == "train"], tab[tab.split == "val"]
    tf_tr, tf_ev = make_tf(IMG_SIZE, mean, std, True), make_tf(IMG_SIZE, mean, std, False)
    epochs = 1 if QUICK else cfg["epochs"]
    dl = loader(tr, tf_tr, cfg["batch"], True)
    # Poids de classe inverses à la fréquence (le rappel sur MALADE compte, mais SAIN ne doit pas être écrasé).
    cnt = np.bincount(tr["y"], minlength=2).astype(float)
    w = torch.tensor(cnt.sum() / (2 * np.maximum(cnt, 1)), dtype=torch.float32, device=DEVICE)
    crit = nn.CrossEntropyLoss(weight=w, label_smoothing=0.05)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=0.05)
    steps = max(1, epochs * len(dl))
    warm = min(len(dl), steps // 10 + 1)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, steps - warm))))
    scaler = torch.amp.GradScaler("cuda", enabled=DEVICE == "cuda")
    state = dict(epoch=0, best_ap=-1.0, history=[], bad=0)
    last = run / "last.pt"
    if RESUME and last.exists():
        ck = torch.load(last, map_location=DEVICE, weights_only=False)
        model.load_state_dict(ck["model"]); opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"]); scaler.load_state_dict(ck["scaler"]); state = ck["state"]
        log(f"{name} : reprise à l'époque {state['epoch']}")
    t_start = time.time()
    patience = 6
    while state["epoch"] < epochs:
        if (time.time() - t_start) / 3600 > cfg["max_hours"] or hours_left() < 0.25:
            log(f"{name} : budget de temps atteint, arrêt à l'époque {state['epoch']}")
            break
        model.train()
        tot, n = 0.0, 0
        for x, y in dl:
            x, y = x.to(DEVICE, non_blocking=True), y.to(DEVICE, non_blocking=True)
            with torch.autocast(device_type="cuda", enabled=DEVICE == "cuda"):
                loss = crit(model(x), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            nn.utils.clip_grad_norm_(model.parameters(), 2.0)
            scaler.step(opt); scaler.update(); sched.step()
            tot += loss.item() * len(y); n += len(y)
        s = predict_torch(model, va, tf_ev)
        ap = safe_auc(average_precision_score, va["y"], s)
        state["epoch"] += 1
        state["history"].append(dict(epoch=state["epoch"], loss=tot / max(n, 1), val_ap=ap))
        log(f"{name} époque {state['epoch']}/{epochs} : perte={tot / max(n, 1):.4f}  AP val={ap:.4f}")
        if not (ap <= state["best_ap"]):          # vrai aussi si ap est NaN au premier passage
            state["best_ap"], state["bad"] = ap, 0
            torch.save(dict(model=model.state_dict(), arch=cfg["arch"], img=IMG_SIZE, mean=mean, std=std,
                            classes=[NEG, POS]), run / "best.pt")
        else:
            state["bad"] += 1
        torch.save(dict(model=model.state_dict(), opt=opt.state_dict(), sched=sched.state_dict(),
                        scaler=scaler.state_dict(), state=state), last)
        if state["bad"] >= patience:
            log(f"{name} : arrêt anticipé (pas de progrès depuis {patience} époques)")
            break
    pd.DataFrame(state["history"]).to_csv(run / "historique.csv", index=False)
    ck = torch.load(run / "best.pt", map_location=DEVICE, weights_only=False)
    model.load_state_dict(ck["model"])
    done = state["epoch"] >= epochs or state["bad"] >= patience
    return model, tf_ev, done


# %%
# ===== 6. DINOv2-small gelé + tête linéaire =====
from sklearn.linear_model import LogisticRegression


class DinoLinear(nn.Module):
    """Tronc DINOv2 gelé + couche linéaire (2 classes) : un seul module, exportable en ONNX au livrable 5."""
    def __init__(self, arch, img, pretrained):
        super().__init__()
        self.backbone = timm.create_model(arch, pretrained=pretrained, num_classes=0, img_size=img)
        self.head = nn.Linear(self.backbone.num_features, 2)

    def forward(self, x):
        return self.head(self.backbone(x))


@torch.no_grad()
def dino_features(model, df, tf, batch):
    model.eval()
    feats = []
    for x, _ in loader(df, tf, batch, False):
        with torch.autocast(device_type="cuda", enabled=DEVICE == "cuda"):
            f = model.backbone(x.to(DEVICE))
        feats.append(f.float().cpu())
    return torch.cat(feats).numpy()


def train_dino(name, cfg, tab):
    run = RUNS / name
    run.mkdir(parents=True, exist_ok=True)
    img = 224 if QUICK else cfg["img"]
    model = DinoLinear(cfg["arch"], img, PRETRAINED).to(DEVICE)
    dc = timm.data.resolve_model_data_config(model.backbone)
    tf = make_tf(img, dc["mean"], dc["std"], False)
    tr, va = tab[tab.split == "train"], tab[tab.split == "val"]
    Xtr, Xva = dino_features(model, tr, tf, cfg["batch"]), dino_features(model, va, tf, cfg["batch"])
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-6
    best = None
    for C in (0.01, 0.1, 1.0, 10.0):       # régularisation choisie sur la validation
        clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit((Xtr - mu) / sd, tr["y"])
        ap = safe_auc(average_precision_score, va["y"], clf.predict_proba((Xva - mu) / sd)[:, 1])
        log(f"{name} : C={C} AP val={ap:.4f}")
        if best is None or ap > best[0]:
            best = (ap, C, clf)
    clf = best[2]
    # Repli de la normalisation dans la couche linéaire : logit = W·((f-mu)/sd) + b → classe 1 vs 0.
    w1 = torch.tensor(clf.coef_[0] / sd, dtype=torch.float32)
    b1 = float(clf.intercept_[0] - (clf.coef_[0] * mu / sd).sum())
    with torch.no_grad():
        model.head.weight.copy_(torch.stack([torch.zeros_like(w1), w1]))
        model.head.bias.copy_(torch.tensor([0.0, b1]))
    torch.save(dict(model=model.state_dict(), arch=cfg["arch"], img=img, mean=dc["mean"], std=dc["std"],
                    classes=[NEG, POS], C=best[1]), run / "best.pt")
    pd.DataFrame([dict(C=best[1], val_ap=best[0])]).to_csv(run / "historique.csv", index=False)
    return model, tf, True


# %%
# ===== 7. YOLO (Ultralytics) : classification et détection =====
from ultralytics import YOLO


def _budget_callback(cfg, flag):
    """Arrête proprement l'entraînement YOLO (fin d'époque) si le budget du modèle ou de la session est épuisé.
    (On n'utilise pas l'argument `time` d'Ultralytics : il ré-estime le nombre d'époques pour remplir tout le temps.)"""
    t0 = time.time()

    def cb(trainer):
        if (time.time() - t0) / 3600 > cfg["max_hours"] or hours_left() < 0.3:
            trainer.stop = True
            flag["coupe"] = True
    return cb


def _yolo_common(name):
    return dict(project=str(RUNS), name=name, exist_ok=True, device=0 if DEVICE == "cuda" else "cpu",
                workers=N_WORKERS, verbose=False, plots=True)


def _yolo_train(name, cfg, data, **hyp):
    """Entraîne (ou reprend) un modèle Ultralytics. Renvoie (modèle best.pt, terminé ?)."""
    run = RUNS / name
    last, fin = run / "weights" / "last.pt", run / "TERMINE"
    flag = {"coupe": False}
    if RESUME and fin.exists():
        log(f"{name} : entraînement déjà terminé, on recharge best.pt")
    elif RESUME and last.exists():
        log(f"{name} : reprise depuis {last}")
        m = YOLO(str(last))
        m.add_callback("on_fit_epoch_end", _budget_callback(cfg, flag))
        m.train(resume=True, device=0 if DEVICE == "cuda" else "cpu", workers=N_WORKERS)
    else:
        if run.exists():
            shutil.rmtree(run)
        m = YOLO(cfg["weights"] if PRETRAINED else cfg["weights"].replace(".pt", ".yaml"))
        m.add_callback("on_fit_epoch_end", _budget_callback(cfg, flag))
        m.train(data=str(data), imgsz=IMG_SIZE, epochs=1 if QUICK else cfg["epochs"], batch=cfg["batch"],
                seed=SEED, cos_lr=True, flipud=0.5, **hyp, **_yolo_common(name))
    if not flag["coupe"]:
        fin.write_text("ok")
    else:
        log(f"{name} : coupé par le budget de temps ; relance le notebook pour continuer")
    return YOLO(str(run / "weights" / "best.pt")), not flag["coupe"]


def _link(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(os.path.abspath(src), dst)
    except OSError:
        shutil.copy2(src, dst)


def quick_cls_dir(tab):
    """Mode test rapide : petit dossier classification (liens vers les vraies images) au format Ultralytics."""
    d = OUT / "cls_rapide"
    shutil.rmtree(d, ignore_errors=True)
    for r in tab.itertuples():
        _link(r.path, d / r.split / (POS if r.y else NEG) / Path(r.path).name)
    return d


def quick_det_yaml(n=24):
    """Mode test rapide : quelques images de détection par ensemble."""
    d = OUT / "det_rapide"
    shutil.rmtree(d, ignore_errors=True)
    src = DATA / "det"
    for sp in ("train", "val", "test"):
        for im in sorted((src / sp / "images").glob("*.jpg"))[:n]:
            _link(im, d / sp / "images" / im.name)
            lb = src / sp / "labels" / (im.stem + ".txt")
            if lb.exists():
                _link(lb, d / sp / "labels" / lb.name)
    y = OUT / "det_rapide.yaml"
    y.write_text(DET_YAML.read_text().replace(f"path: {src}", f"path: {d}"))
    return y


def train_yolo_cls(name, cfg, tab):
    data = quick_cls_dir(tab) if QUICK else DATA / "cls"
    return _yolo_train(name, cfg, data, patience=8)


def train_yolo_det(name, cfg, tab):
    if DET_YAML is None:
        return None, False
    data = quick_det_yaml() if QUICK else DET_YAML
    return _yolo_train(name, cfg, data, patience=15, degrees=10)


def predict_yolo(model, df, kind, batch=32):
    """Score image : probabilité « malade » (classif) ou confiance de la boîte la plus sûre (détection, 0 si aucune)."""
    scores = []
    paths = df["path"].tolist()
    pos_idx = None
    if kind == "yolo_cls":
        pos_idx = [k for k, v in model.names.items() if v == POS][0]
    for i in range(0, len(paths), batch):
        res = model.predict(paths[i:i + batch], imgsz=IMG_SIZE, conf=0.001, verbose=False,
                            device=0 if DEVICE == "cuda" else "cpu")
        for r in res:
            if kind == "yolo_cls":
                scores.append(float(r.probs.data[pos_idx]))
            else:
                c = r.boxes.conf
                scores.append(float(c.max()) if len(c) else 0.0)
    return np.array(scores)


def det_metrics(model):
    """mAP de détection sur le test (indicatif : seules les images avec boîtes y sont)."""
    y = (OUT / "det_rapide.yaml") if QUICK else DET_YAML
    if y is None or not y.exists() or "test:" not in y.read_text():
        return {}
    m = model.val(data=str(y), split="test", imgsz=IMG_SIZE, verbose=False, plots=False,
                  device=0 if DEVICE == "cuda" else "cpu", project=str(RUNS), name="_val_tmp", exist_ok=True)
    return dict(det_map50=float(m.box.map50), det_map50_95=float(m.box.map), det_P=float(m.box.mp), det_R=float(m.box.mr))


# %%
# ===== 8. TEMPS D'INFÉRENCE CPU (indicatif : le vrai chronométrage ONNX se fait au livrable 5) =====
def cpu_latency_torch(model, img, n=20):
    m = model.to("cpu").eval()
    torch.set_num_threads(4)
    x = torch.randn(1, 3, img, img)
    with torch.no_grad():
        for _ in range(3):
            m(x)
        t = time.perf_counter()
        for _ in range(n):
            m(x)
    m.to(DEVICE)
    return (time.perf_counter() - t) / n * 1000


def cpu_latency_yolo(model, path, n=10):
    torch.set_num_threads(4)
    for _ in range(2):
        model.predict(path, imgsz=IMG_SIZE, device="cpu", verbose=False)
    t = time.perf_counter()
    for _ in range(n):
        model.predict(path, imgsz=IMG_SIZE, device="cpu", verbose=False)
    return (time.perf_counter() - t) / n * 1000


def n_params(m):
    return sum(p.numel() for p in m.parameters()) / 1e6


# %%
# ===== 9. BOUCLE PRINCIPALE : entraîner, prédire val/test, résumer =====
def evaluate_model(name, kind, scores_val, scores_test, extra):
    va = TABLE[TABLE.split == "val"].copy(); va["score"] = scores_val
    te = TABLE[TABLE.split == "test"].copy(); te["score"] = scores_test
    va.to_csv(RES / "preds" / f"{name}_val.csv", index=False)
    te.to_csv(RES / "preds" / f"{name}_test.csv", index=False)
    t = choose_threshold(va["y"], va["score"])
    mv, mt = metrics_at(va["y"], va["score"], t), metrics_at(te["y"], te["score"], t)
    (rci, pci) = group_bootstrap(te, t, n=100 if QUICK else 500)
    row = dict(modele=name, type=kind, seuil=t,
               val_AP=safe_auc(average_precision_score, va["y"], va["score"]),
               val_rappel=mv["recall"], val_precision=mv["precision"],
               test_AP=safe_auc(average_precision_score, te["y"], te["score"]),
               test_AUROC=safe_auc(roc_auc_score, te["y"], te["score"]),
               test_rappel=mt["recall"], test_rappel_IC95=f"[{rci[0]:.3f} ; {rci[1]:.3f}]",
               test_precision=mt["precision"], test_precision_IC95=f"[{pci[0]:.3f} ; {pci[1]:.3f}]",
               test_F1=mt["f1"], test_F2=mt["f2"], test_specificite=mt["specificity"],
               test_TP=mt["tp"], test_FP=mt["fp"], test_FN=mt["fn"], test_TN=mt["tn"], **extra)
    # Détail par source et par maladie (étiquette fine) au même seuil.
    per = []
    for (col, key), g in [(("source", k), g) for k, g in te.groupby("source")] + [(("fine", k), g) for k, g in te.groupby("fine")]:
        m = metrics_at(g["y"], g["score"], t)
        per.append(dict(modele=name, axe=col, valeur=key, n=len(g), n_malade=int(g["y"].sum()),
                        rappel=m["recall"], precision=m["precision"], specificite=m["specificity"]))
    return row, per


def run_all():
    rows, per_rows = [], []
    done_file = RES / "modeles_termines.json"
    done = json.loads(done_file.read_text()) if (RESUME and done_file.exists()) else {}
    for name, cfg in MODELS.items():
        if not cfg["enabled"]:
            continue
        if name in done:
            log(f"{name} : déjà terminé, résultats repris")
            rows.append(done[name]["row"]); per_rows += done[name]["per"]
            continue
        if hours_left() < 0.4:
            log(f"{name} : plus assez de temps dans cette session (relance le notebook pour continuer)")
            continue
        log(f"===== {name} =====")
        seed_all()
        va, te = TABLE[TABLE.split == "val"], TABLE[TABLE.split == "test"]
        kind = cfg["kind"]
        try:
            if kind in ("timm", "dino_lin"):
                model, tf, finished = (train_timm if kind == "timm" else train_dino)(name, cfg, TABLE)
                sv, st = predict_torch(model, va, tf), predict_torch(model, te, tf)
                img = torch.load(RUNS / name / "best.pt", weights_only=False)["img"]
                extra = dict(params_M=n_params(model), cpu_ms_img=cpu_latency_torch(model, img), img=img)
                shutil.copy2(RUNS / name / "best.pt", EXPORT / f"{name}.pt")
            else:
                model, finished = (train_yolo_cls if kind == "yolo_cls" else train_yolo_det)(name, cfg, TABLE)
                if model is None:
                    continue
                sv, st = predict_yolo(model, va, kind), predict_yolo(model, te, kind)
                extra = dict(params_M=n_params(model.model), img=IMG_SIZE,
                             cpu_ms_img=cpu_latency_yolo(model, te["path"].iloc[0]))
                if kind == "yolo_det":
                    extra.update(det_metrics(model))
                shutil.copy2(RUNS / name / "weights" / "best.pt", EXPORT / f"{name}.pt")
        except Exception as e:  # un modèle qui échoue ne doit pas faire perdre les autres
            log(f"{name} : ÉCHEC → {type(e).__name__}: {e}")
            continue
        row, per = evaluate_model(name, kind, sv, st, extra)
        rows.append(row); per_rows += per
        json.dump(dict(modele=name, type=kind, seuil=row["seuil"], img=extra["img"], classes=[NEG, POS],
                       score="proba_malade" if kind != "yolo_det" else "max_conf_boite"),
                  open(EXPORT / f"{name}.json", "w"), indent=1)
        if finished:
            done[name] = dict(row=row, per=per)
            done_file.write_text(json.dumps(done, indent=1, default=float))
        log(f"{name} : AP val={row['val_AP']:.3f} | test rappel={row['test_rappel']:.3f} "
            f"précision={row['test_precision']:.3f} (seuil {row['seuil']:.3f})")
    return pd.DataFrame(rows), pd.DataFrame(per_rows)


RESULTS, PER = run_all()

# %%
# ===== 10. RAPPORT DE COMPARAISON + CHOIX DU MODÈLE (sur la validation) =====
def md_table(df):
    """Tableau Markdown sans dépendance (pandas.to_markdown exige le paquet tabulate)."""
    f = lambda v: f"{v:.3f}" if isinstance(v, (float, np.floating)) else str(v)
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    lines += ["| " + " | ".join(f(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(lines)


def pick_model(res):
    """Règle : meilleure précision VALIDATION au seuil qui donne le rappel cible ; à 0,01 près → le plus rapide sur CPU."""
    r = res.dropna(subset=["val_precision"]).sort_values("val_precision", ascending=False)
    if r.empty:
        return None
    top = r[r["val_precision"] >= r["val_precision"].iloc[0] - 0.01]
    return top.sort_values("cpu_ms_img").iloc[0]["modele"]


def pr_plot(res):
    fig, ax = plt.subplots(figsize=(6.5, 5))
    for name in res["modele"]:
        te = pd.read_csv(RES / "preds" / f"{name}_test.csv")
        if te["y"].nunique() < 2:
            continue
        p, r, _ = precision_recall_curve(te["y"], te["score"])
        ax.plot(r, p, label=f"{name} (AP={average_precision_score(te['y'], te['score']):.3f})")
    ax.axvline(RECALL_TARGET, ls="--", c="grey", lw=1)
    ax.set_xlabel("rappel (MALADE_OU_RAVAGEUR)"); ax.set_ylabel("précision"); ax.set_title("Courbes précision-rappel — test")
    ax.legend(fontsize=8); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(RES / "pr_test.png", dpi=130); plt.close(fig)


if len(RESULTS):
    RESULTS.to_csv(RES / "comparaison.csv", index=False)
    PER.to_csv(RES / "detail_par_source_et_maladie.csv", index=False)
    pr_plot(RESULTS)
    choice = pick_model(RESULTS)
    json.dump(dict(modele=choice, regle="précision val max au rappel cible ; égalité (0,01) → plus rapide CPU",
                   rappel_cible=RECALL_TARGET, mode=MODE), open(RES / "choix_modele.json", "w"), indent=1)
    cols = ["modele", "val_AP", "test_AP", "seuil", "test_rappel", "test_rappel_IC95", "test_precision",
            "test_precision_IC95", "test_F1", "test_specificite", "det_map50", "params_M", "cpu_ms_img"]
    show = RESULTS[[c for c in cols if c in RESULTS]].copy()
    print("\n===== COMPARAISON (seuil choisi sur la validation pour un rappel ≥ "
          f"{RECALL_TARGET:.0%}) =====")
    print(show.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\n===== DÉTAIL TEST par source / maladie (même seuil) =====")
    print(PER.pivot_table(index=["axe", "valeur"], columns="modele", values="rappel").to_string(float_format=lambda v: f"{v:.2f}"))
    print(f"\nModèle retenu (règle sur la validation) : {choice}")
    md = ["# Comparaison des modèles — maïs SAIN / MALADE_OU_RAVAGEUR", "",
          f"- Mode : {MODE} ; rappel cible : {RECALL_TARGET:.0%} ; seuil fixé sur la validation ; appareil : {DEVICE}",
          f"- Modèle retenu : **{choice}**", "", md_table(show), "",
          "Intervalles à 95 % : bootstrap par groupes d'images (500 tirages).",
          "Temps CPU : PyTorch, 4 fils, image par image, sur le CPU de Kaggle (indicatif ; voir livrable 5).", "",
          "![PR](pr_test.png)"]
    (RES / "comparaison.md").write_text("\n".join(md))
    log("résultats écrits dans", RES)
else:
    log("aucun modèle évalué")

# %%
# ===== 11. RÉCAPITULATIF DES FICHIERS PRODUITS =====
for p in sorted(OUT.rglob("*")):
    if p.is_file() and p.suffix in {".csv", ".md", ".png", ".json", ".pt"} and "runs" not in p.parts:
        print(f"{p.relative_to(OUT)}  ({p.stat().st_size / 1e6:.1f} Mo)")
log("Fin. Temps total :", f"{(time.time() - T0) / 3600:.2f} h")
