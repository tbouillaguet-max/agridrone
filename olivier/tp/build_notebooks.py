"""Génère les notebooks du TP « maladies et parasites de l'olivier ».

Une seule source pour deux versions : chaque exercice a un squelette (version élève,
``olivier/tp/``) et une solution (corrigé, ``olivier/tp/corriges/``). Après une modification :

    uv run python olivier/tp/build_notebooks.py

Ne pas modifier les notebooks à la main : les changements seraient écrasés.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

HERE = Path(__file__).resolve().parent

# Une cellule : ("md", texte) | ("code", code) | ("exo", squelette, solution)
Cell = tuple[str, ...]


def md(text: str) -> Cell:
    return ("md", dedent(text).strip())


def code(src: str) -> Cell:
    return ("code", dedent(src).strip())


def exo(stub: str, solution: str) -> Cell:
    return ("exo", dedent(stub).strip(), dedent(solution).strip())


def build(cells: list[Cell], corrige: bool) -> nbformat.NotebookNode:
    nb = new_notebook()
    nb.metadata["kernelspec"] = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    nb.metadata["language_info"] = {"name": "python"}
    out = []
    for cell in cells:
        if cell[0] == "md":
            out.append(new_markdown_cell(cell[1]))
        elif cell[0] == "code":
            out.append(new_code_cell(cell[1]))
        else:
            src = cell[2] if corrige else cell[1]
            header = (
                "# Corrigé\n"
                if corrige
                else "# À FAIRE : complétez cette cellule, puis exécutez-la.\n"
            )
            out.append(new_code_cell(header + src))
    nb.cells = out
    return nb


# ======================================================================
# Code commun : trouver la racine du projet, graines, matériel
# ======================================================================

SETUP_COMMON = """
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch

# Racine du projet : le dossier qui contient pyproject.toml (le notebook peut être lancé
# depuis olivier/tp/ ou olivier/tp/corriges/).
ROOT = Path.cwd().resolve()
while not (ROOT / "pyproject.toml").exists() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
# Données extraites par `agridrone data download --project olivier`. Si vous les avez
# mises sur un autre disque (olivier/configs/local.yaml), remplacez par votre chemin,
# ex. Path("D:/agridrone/olivier/interim").
DATA = ROOT / "data" / "olivier" / "interim"

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

if torch.cuda.is_available():
    DEVICE = "cuda"
elif torch.backends.mps.is_available():
    DEVICE = "mps"
else:
    DEVICE = "cpu"
# Sous Windows et macOS, les DataLoader à plusieurs processus ne fonctionnent pas avec des
# classes définies dans un notebook : on charge les images dans le processus principal.
NUM_WORKERS = 2 if sys.platform.startswith("linux") else 0
# Sans GPU NVIDIA (CPU, ou GPU de Mac), entraînement raccourci.
MODE_RAPIDE = DEVICE != "cuda"
print(f"Projet : {ROOT}\\nMatériel : {DEVICE} ; MODE_RAPIDE = {MODE_RAPIDE}")
"""

# ======================================================================
# TP 1 : maladies et acariens des feuilles
# ======================================================================

TP1: list[Cell] = [
    md("""
    # TP 1 : reconnaître les maladies et les acariens des feuilles d'olivier

    **Objectif.** Construire un classifieur d'images qui distingue trois états d'une
    feuille d'olivier :

    | Classe | Cause | Ce qu'on voit |
    |---|---|---|
    | `sain` | — | feuille verte, uniforme |
    | `oeil_de_paon` | champignon *Venturia oleaginea* | taches rondes brunes cerclées de jaune |
    | `acariose` | acarien *Aculus olearius* (un parasite) | feuille déformée, décolorée, gaufrée |

    Puis vérifier honnêtement ce que vaut ce modèle : doublons, fuites entre
    entraînement et test, incertitude, et surtout **images venues d'ailleurs**.

    **Ce que vous allez apprendre.**

    1. Explorer un jeu d'images et trouver ses pièges (doublons, fonds, déséquilibre).
    2. Découper train / validation / test sans fuite.
    3. Poser une référence simple (histogrammes de couleur + régression logistique).
    4. Entraîner un réseau pré-entraîné (*transfer learning*) avec PyTorch et timm.
    5. Évaluer : matrice de confusion, rappel par classe, seuil « incertain ».
    6. Tester sur des feuilles d'autres sources (autres photographes en Turquie, Pérou) :
       le vrai test.
    7. Voir où regarde le réseau (Grad-CAM), sauvegarder et réutiliser le modèle.

    **Comment travailler.** Commencez par enregistrer ce notebook sous un autre nom
    (Fichier > Enregistrer sous…). Les cellules marquées « À FAIRE » sont à compléter. Les
    questions ❓ sont à traiter dans votre compte rendu. Le corrigé est dans
    `olivier/tp/corriges/`. Ne l'ouvrez qu'après avoir essayé.

    **Données** (à télécharger une fois, depuis la racine du projet, dans un terminal) :

    ```bash
    uv run agridrone data download olive_leaf_uguz_uysal olive_leaf_peacock_diker olive_leaf_peacock_peru
    ```
    """),
    md("## 0. Mise en route"),
    code(
        SETUP_COMMON
        + """
import hashlib
import time

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image, ImageOps

OUT = ROOT / "runs" / "olivier" / "tp1"
OUT.mkdir(parents=True, exist_ok=True)

# Réglages : sur CPU, environ 2 minutes par époque (CPU 4 cœurs) ; sur GPU, moins d'une minute.
IMG_SIZE = 192 if MODE_RAPIDE else 224
EPOCHS = 8 if MODE_RAPIDE else 15
BATCH = 32
ARCH = "efficientnet_b0.ra_in1k"   # 5,3 M de paramètres, poids ImageNet
CLASSES = ["sain", "oeil_de_paon", "acariose"]
print(f"IMG_SIZE={IMG_SIZE}, EPOCHS={EPOCHS}")
"""
    ),
    md("""
    ## 1. Les données

    Le jeu d'Uğuz et Uysal (Denizli, Turquie, 2019) contient 3 400 photos de feuilles en
    cinq archives. Les auteurs fournissent un découpage « officiel » : des archives
    d'entraînement et une archive de test. Deux dossiers ne portent pas de nom de classe
    (`train3`, `train4`) : ce sont des feuilles atteintes d'œil de paon (vérifié à l'œil).
    """),
    code("""
UGUZ = DATA / "olive_leaf_uguz_uysal"
DOSSIERS = {  # dossier -> (classe, découpage officiel)
    "Train1/Healthy": ("sain", "train"),
    "Train2/aculus_olearius": ("acariose", "train"),
    "train3/train3": ("oeil_de_paon", "train"),
    "train4/train4": ("oeil_de_paon", "train"),
    "test/test/Healthy": ("sain", "test"),
    "test/test/aculus_olearius": ("acariose", "test"),
    "test/test/olive_peacock_spot": ("oeil_de_paon", "test"),
}
EXTENSIONS = {".jpg", ".jpeg", ".png"}

lignes = []
for dossier, (classe, officiel) in DOSSIERS.items():
    for f in sorted((UGUZ / dossier).iterdir()):
        if f.suffix.lower() in EXTENSIONS:
            lignes.append({"chemin": f, "classe": classe, "officiel": officiel})
df = pd.DataFrame(lignes)
print(len(df), "images")
df.head()
"""),
    md("""
    ### Exercice 1.1 : combien d'images par classe ?

    Affichez un tableau croisé classe × découpage officiel (`pd.crosstab`) et un
    diagramme en barres. Les classes sont-elles équilibrées ?
    """),
    exo(
        """
# tableau = pd.crosstab(...)
# tableau.plot.bar(...)
""",
        """
tableau = pd.crosstab(df["classe"], df["officiel"], margins=True)
display(tableau)
pd.crosstab(df["classe"], df["officiel"]).plot.bar(figsize=(6, 3), rot=0)
plt.ylabel("images")
plt.title("Images par classe et par découpage officiel")
plt.show()
""",
    ),
    md("""
    ### Exercice 1.2 : regarder les images

    Écrivez `montrer(df, n)`, qui affiche `n` images tirées au hasard pour chaque classe.

    ❓ Quels indices visuels distinguent les classes ? Sur quel fond sont prises les
    photos ? Pourquoi est-ce un risque pour un modèle destiné à des images prises au
    champ ou par drone ?
    """),
    exo(
        """
def montrer(df, n=5, graine=0):
    ...  # une ligne par classe, n images par ligne (plt.subplots, ax.imshow, ax.axis("off"))

montrer(df)
""",
        """
def montrer(df, n=5, graine=0):
    classes = sorted(df["classe"].unique())
    fig, axes = plt.subplots(len(classes), n, figsize=(2.6 * n, 2.2 * len(classes)), squeeze=False)
    for i, classe in enumerate(classes):
        tirage = df[df["classe"] == classe].sample(n, random_state=graine)
        for j, chemin in enumerate(tirage["chemin"]):
            ax = axes[i, j]
            ax.imshow(Image.open(chemin))
            ax.axis("off")
            if j == 0:
                ax.set_title(classe, loc="left", fontsize=10)
    plt.tight_layout()
    plt.show()

montrer(df)
""",
    ),
    md("""
    ### Exercice 1.3 : les doublons exacts

    Une même photo présente deux fois peut se retrouver à la fois en entraînement et en
    test. Le modèle est alors évalué sur des images qu'il a apprises : c'est une
    **fuite**, qui gonfle les scores.

    Calculez l'empreinte MD5 de chaque fichier (`hashlib.md5(chemin.read_bytes())`),
    puis comptez :

    - le nombre de copies en trop (fichiers − empreintes distinctes) ;
    - le nombre de photos (empreintes) présentes **à la fois** dans le train et le test
      officiels ;
    - le nombre de photos rangées dans deux classes différentes.
    """),
    exo(
        """
# df["md5"] = ...
# nb_doublons = ...
# fuites = ...      # empreintes présentes dans les deux découpages officiels
# conflits = ...    # empreintes associées à deux classes
""",
        """
df["md5"] = [hashlib.md5(p.read_bytes()).hexdigest() for p in df["chemin"]]
nb_doublons = len(df) - df["md5"].nunique()
par_empreinte = df.groupby("md5")
fuites = par_empreinte["officiel"].nunique()
fuites = fuites[fuites > 1].index
conflits = par_empreinte["classe"].nunique()
conflits = conflits[conflits > 1].index
print(f"copies en trop : {nb_doublons}")
print(f"photos à la fois en train et en test : {len(fuites)}")
print(f"photos rangées dans deux classes : {len(conflits)}")
""",
    ),
    md("""
    ### Exercice 1.4 : les quasi-doublons

    Une photo recadrée, réduite ou réenregistrée n'a plus la même empreinte MD5, mais
    c'est la même image. On la repère avec une **empreinte perceptuelle** (*dHash*) :

    1. passer l'image en niveaux de gris, réduite à 17 pixels de large sur 16 de haut
       (`im.resize((taille + 1, taille))` ; numpy rendra un tableau de 16 lignes et 17
       colonnes) ;
    2. comparer chaque pixel à son voisin de droite, ce qui donne 16 × 16 = 256 bits ;
    3. deux images sont quasi identiques si très peu de bits diffèrent. Le nombre de bits
       différents s'appelle la **distance de Hamming**.

    Complétez `dhash`. Le reste est fourni :
    - la matrice des distances, calculée par blocs pour ménager la mémoire ;
    - le regroupement (algorithme *union-find*) : deux images à distance ≤ `SEUIL` vont
      dans le même **groupe**, et les liens s'enchaînent. Si A est proche de B et B proche
      de C, alors A, B et C forment un seul groupe, même si A et C sont très différentes ;
    - une planche de paires d'images par tranche de distance.

    Ces groupes serviront au découpage : un groupe entier va soit en entraînement, soit en
    validation.
    """),
    exo(
        '''
def dhash(chemin, taille=16):
    """Empreinte perceptuelle : vecteur numpy 1D de taille*taille booléens (pensez à .flatten())."""
    ...
''',
        '''
def dhash(chemin, taille=16):
    """Empreinte perceptuelle : vecteur numpy 1D de taille*taille booléens (pensez à .flatten())."""
    im = Image.open(chemin)
    im.draft("L", (4 * taille, 4 * taille))  # JPEG : décodage réduit, plus rapide
    a = np.asarray(im.convert("L").resize((taille + 1, taille), Image.BILINEAR), dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten()
''',
    ),
    code('''
# Fourni : distances de Hamming entre toutes les paires, par blocs de 256 images.
assert dhash(df["chemin"].iloc[0]).shape == (256,), "dhash doit renvoyer un vecteur de 256 booléens"
empreintes = np.packbits(np.stack([dhash(p) for p in df["chemin"]]), axis=1)   # (n, 32) octets
n = len(empreintes)
distances = np.zeros((n, n), dtype=np.uint16)
for debut in range(0, n, 256):
    bloc = empreintes[debut:debut + 256, None, :] ^ empreintes[None, :, :]
    distances[debut:debut + 256] = np.bitwise_count(bloc).sum(axis=-1)

def grouper(seuil):
    """Union-find : relie les images à distance <= seuil. Renvoie un numéro de groupe par image."""
    parent = list(range(n))
    def racine(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, j in zip(*np.nonzero(np.triu(distances <= seuil, k=1))):
        parent[racine(i)] = racine(j)
    return np.array([racine(i) for i in range(n)])

def voir_paires(d_min, d_max, k=4, graine=0):
    """Affiche k paires d'images (MD5 différents) dont la distance est entre d_min et d_max."""
    i, j = np.nonzero(np.triu((distances >= d_min) & (distances <= d_max), k=1))
    garde = df["md5"].values[i] != df["md5"].values[j]
    i, j = i[garde], j[garde]
    print(f"{len(i)} paires à distance {d_min}-{d_max}")
    if len(i) == 0:
        return
    tirage = np.random.default_rng(graine).choice(len(i), size=min(k, len(i)), replace=False)
    fig, axes = plt.subplots(1, 2 * len(tirage), figsize=(2.4 * 2 * len(tirage), 2), squeeze=False)
    for m, t in enumerate(tirage):
        for c, idx in enumerate((i[t], j[t])):
            ax = axes[0, 2 * m + c]
            ax.imshow(Image.open(df["chemin"].iloc[idx]))
            ax.set_title(f"{df['officiel'].iloc[idx]} / {df['classe'].iloc[idx]}", fontsize=7)
            ax.axis("off")
    plt.show()

for seuil in (0, 3, 10, 20, 30):
    g = grouper(seuil)
    tailles = pd.Series(g).value_counts()
    a_cheval = pd.DataFrame({"g": g, "o": df["officiel"]}).groupby("g")["o"].nunique().gt(1).sum()
    print(f"seuil {seuil:2d} : plus grand groupe {tailles.max():5d} images, "
          f"{a_cheval} groupes à cheval sur train et test")
'''),
    md("""
    ### Exercice 1.5 : choisir le seuil en regardant

    Affichez des paires à distance 0, 1-4, 5-9 et 10-20 avec `voir_paires`. À partir de
    quelle distance ne s'agit-il plus de la même photo ?

    ❓ Que se passe-t-il avec un seuil trop large (20, 30) ? Pourquoi des photos prises
    sur quelques fonds identiques (papier blanc, bois) piègent-elles une empreinte aussi
    simple ? La même feuille, reprise en photo un peu décalée, est-elle repérée ? Proposez
    une méthode plus robuste, par exemple comparer les sorties d'un réseau pré-entraîné.
    """),
    exo(
        """
# voir_paires(0, 0) ; voir_paires(1, 4) ; ...
SEUIL = ...   # votre choix
df["groupe"] = grouper(SEUIL)
""",
        """
for d_min, d_max in [(0, 0), (1, 4), (5, 9), (10, 20)]:
    voir_paires(d_min, d_max)
# Distance 0 : la même photo réenregistrée. De 1 à 4 : très peu de paires, en partie la
# même feuille légèrement décalée, en partie des feuilles voisines sur le même fond. Dès 5 :
# presque toujours des feuilles différentes. Un seuil bas (3) attrape les vraies copies et ne
# relie à tort que quelques paires ; plus haut, les groupes s'enchaînent (« A ressemble à B,
# qui ressemble à C ») et des centaines de feuilles différentes se retrouvent liées.
SEUIL = 3
df["groupe"] = grouper(SEUIL)
melanges = df.groupby("groupe")["officiel"].nunique()
print(f"seuil {SEUIL} : {df['groupe'].nunique()} groupes ; "
      f"{(melanges > 1).sum()} groupes à cheval sur le train et le test officiels")
""",
    ),
    md("""
    ❓ Le MD5 trouvait 24 photos présentes à la fois dans le train et le test officiels.
    Avec les quasi-doublons, combien de groupes sont à cheval sur les deux, et combien
    d'images du test officiel cela retire-t-il (partie 2) ? Qu'en concluez-vous sur les
    scores publiés avec ce découpage officiel ?

    ## 2. Découper sans fuite

    Règles retenues :

    - **test** = le test officiel, **moins** les images dont une copie (quasi) identique
      est dans le train officiel (futur entraînement ou validation) ;
    - **validation** = 20 % des groupes du train officiel, tirés par classe
      (`StratifiedGroupKFold`) ; elle sert à choisir l'époque et les seuils ;
    - **entraînement** = le reste, sans doublon exact.
    """),
    exo(
        """
from sklearn.model_selection import StratifiedGroupKFold

# 1. groupes présents dans le train officiel
# 2. test = test officiel dont le groupe n'est pas dans le train officiel, sans doublon (md5)
# 3. officiel_train = train officiel dédoublonné (drop_duplicates sur "md5")
# 4. idx_train, idx_val = next(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
#                                .split(officiel_train, officiel_train["classe"], officiel_train["groupe"]))
# train, val, test = ...
""",
        """
from sklearn.model_selection import StratifiedGroupKFold

groupes_train = set(df.loc[df["officiel"] == "train", "groupe"])
test = df[(df["officiel"] == "test") & ~df["groupe"].isin(groupes_train)].drop_duplicates("md5")
officiel_train = df[df["officiel"] == "train"].drop_duplicates("md5").reset_index(drop=True)

sgkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEED)
idx_train, idx_val = next(sgkf.split(officiel_train, officiel_train["classe"], officiel_train["groupe"]))
train = officiel_train.iloc[idx_train].reset_index(drop=True)
val = officiel_train.iloc[idx_val].reset_index(drop=True)
test = test.reset_index(drop=True)

assert not set(train["groupe"]) & set(val["groupe"])
assert not set(train["groupe"]) & set(test["groupe"])
print(pd.DataFrame({n: d["classe"].value_counts() for n, d in [("train", train), ("val", val), ("test", test)]}))
""",
    ),
    md("""
    ## 3. Une référence sans deep learning

    Avant un réseau de neurones, posez une **référence** simple : si elle fait déjà 95 %,
    le problème est facile, ou biaisé. Ici, chaque image est résumée par l'histogramme de
    ses couleurs (teinte, saturation, valeur), classé par une régression logistique.

    Pour chaque classe :
    - le **rappel** est la part des images de cette classe correctement reconnues ;
    - la **précision** est la part des images prédites dans cette classe qui en sont
      vraiment ;
    - le **F1** est la moyenne harmonique des deux.

    ### Exercice 3.1

    Complétez `histo_hsv`, entraînez la régression sur `train`, puis évaluez-la sur `val`
    (`classification_report` donne exactitude, précision, rappel et F1 par classe).
    """),
    exo(
        '''
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

def histo_hsv(chemin, bins=16):
    """Concatène les histogrammes normalisés des 3 canaux HSV (3 x bins valeurs)."""
    ...

# X_train = np.stack([...]) ; X_val = ...
# reference = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
# reference.fit(...) ; print(classification_report(...))
''',
        '''
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

def histo_hsv(chemin, bins=16):
    """Concatène les histogrammes normalisés des 3 canaux HSV (3 x bins valeurs)."""
    im = Image.open(chemin)
    im.draft("RGB", (320, 240))  # décodage JPEG réduit : beaucoup plus rapide
    a = np.asarray(im.convert("HSV").resize((256, 192)))
    return np.concatenate(
        [np.histogram(a[..., c], bins=bins, range=(0, 256), density=True)[0] for c in range(3)]
    )

X_train = np.stack([histo_hsv(p) for p in train["chemin"]])
X_val = np.stack([histo_hsv(p) for p in val["chemin"]])
reference = make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced"))
reference.fit(X_train, train["classe"])
print(classification_report(val["classe"], reference.predict(X_val), digits=3))
''',
    ),
    md("""
    ❓ Quelle classe la couleur seule reconnaît-elle le mieux, et laquelle le moins bien ?
    Proposez une explication à partir des images de l'exercice 1.2 (couleur des taches,
    déformation, fond).

    ## 4. Un réseau pré-entraîné (*transfer learning*)

    On part d'EfficientNet-B0, entraîné sur ImageNet (1,2 million de photos) : ses
    premières couches savent déjà détecter bords, textures et formes. On remplace sa
    dernière couche par une couche à 3 sorties, puis on réentraîne tout le réseau sur
    nos feuilles.

    ### 4.1 Le jeu de données PyTorch et les augmentations (fourni)

    Les augmentations (recadrage, rotations, retournements, couleur) montrent au réseau des
    variantes de chaque photo : il apprend des motifs plutôt que des pixels précis.

    Pour l'évaluation, `au_format` complète d'abord chaque image au format 4:3 avec la
    couleur de ses bords. Sans cela, une photo très allongée (les feuilles de la partie 6
    font 1920 × 540) serait recadrée au centre, et le réseau ne verrait qu'un quart de la
    feuille.
    """),
    code('''
import timm
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T

def au_format(im, ratio=4 / 3):
    """Complète l'image avec la couleur de ses bords pour la ramener au format 4:3."""
    w, h = im.size
    grand, petit = max(w, h), min(w, h)
    grand2, petit2 = max(grand, round(petit * ratio)), max(petit, round(grand / ratio))
    taille = (grand2, petit2) if w >= h else (petit2, grand2)
    if taille == (w, h):
        return im
    a = np.asarray(im)
    bords = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return ImageOps.pad(im, taille, color=tuple(int(v) for v in np.median(bords, axis=0)))

MOYENNE, ECART = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)  # normalisation ImageNet
tf_train = T.Compose([
    T.RandomResizedCrop(IMG_SIZE, scale=(0.6, 1.0)),
    T.RandomHorizontalFlip(),
    T.RandomVerticalFlip(),
    T.RandomRotation(20),
    T.ColorJitter(0.2, 0.2, 0.2, 0.02),
    T.ToTensor(),
    T.Normalize(MOYENNE, ECART),
])

def transformation_eval(taille):
    return T.Compose([
        T.Lambda(au_format),
        T.Resize(int(taille * 1.15)),
        T.CenterCrop(taille),
        T.ToTensor(),
        T.Normalize(MOYENNE, ECART),
    ])

tf_eval = transformation_eval(IMG_SIZE)

class Feuilles(Dataset):
    def __init__(self, chemins, etiquettes, transform):
        self.chemins, self.etiquettes, self.transform = list(chemins), list(etiquettes), transform

    def __len__(self):
        return len(self.chemins)

    def __getitem__(self, i):
        im = Image.open(self.chemins[i])
        im.draft("RGB", (2 * IMG_SIZE, 2 * IMG_SIZE))  # JPEG : décodage réduit, plus rapide
        return self.transform(im.convert("RGB")), self.etiquettes[i]

def chargeur(d, transform, melanger=False):
    y = [CLASSES.index(c) for c in d["classe"]]
    return DataLoader(Feuilles(d["chemin"], y, transform), batch_size=BATCH, shuffle=melanger,
                      num_workers=NUM_WORKERS)

dl_train = chargeur(train, tf_train, melanger=True)
dl_val, dl_test = chargeur(val, tf_eval), chargeur(test, tf_eval)
x, y = next(iter(dl_train))
print(x.shape, y[:10])
'''),
    md("""
    ### Exercice 4.2 : la boucle d'entraînement

    C'est le cœur de tout entraînement PyTorch. Écrivez :

    - `entrainer_une_epoque(modele, chargeur, optimiseur, critere)` : pour chaque lot,
      remettre les gradients à zéro, calculer la perte, rétropropager, faire un pas
      d'optimisation. Renvoyer la perte moyenne et l'exactitude ;
    - `predire(modele, chargeur)` : en mode évaluation et sans gradient, renvoyer les
      probabilités (softmax) et les vraies étiquettes.

    Envoyez chaque lot sur le matériel avec `x.to(DEVICE)`. Ramenez les probabilités sur
    le CPU (`.cpu()`) avant `.numpy()`.
    """),
    exo(
        """
def entrainer_une_epoque(modele, chargeur, optimiseur, critere):
    modele.train()
    ...
    return perte_moyenne, exactitude

@torch.no_grad()
def predire(modele, chargeur):
    modele.eval()
    ...
    return probas, etiquettes   # tableaux numpy (n, 3) et (n,)
""",
        """
def entrainer_une_epoque(modele, chargeur, optimiseur, critere):
    modele.train()
    somme, n, justes = 0.0, 0, 0
    for x, y in chargeur:
        x, y = x.to(DEVICE), y.to(DEVICE)
        optimiseur.zero_grad()
        logits = modele(x)
        perte = critere(logits, y)
        perte.backward()
        optimiseur.step()
        somme += perte.item() * len(y)
        n += len(y)
        justes += (logits.argmax(1) == y).sum().item()
    return somme / n, justes / n

@torch.no_grad()
def predire(modele, chargeur):
    modele.eval()
    probas, etiquettes = [], []
    for x, y in chargeur:
        probas.append(torch.softmax(modele(x.to(DEVICE)), dim=1).cpu())
        etiquettes.append(y)
    return torch.cat(probas).numpy(), torch.cat(etiquettes).numpy()
""",
    ),
    md("""
    ### 4.3 Entraîner

    - **Poids de classe** : la perte pèse davantage les classes rares.
    - **Lissage des étiquettes** (coefficient 0,1) : la cible n'est plus 100 % pour la bonne
      classe, mais environ 93 %. Le réseau devient moins sûr de lui et sur-apprend moins.
      Gardez-le en tête à la partie 5 : ses probabilités ne sont pas pour autant des
      fréquences fiables.
    - **Taux d'apprentissage** en cosinus : il décroît doucement jusqu'à la fin.
    - **On garde la meilleure époque** sur la validation (pas la dernière), puis on
      recalcule les probabilités de validation avec ce modèle.

    Durée indicative : environ 2 minutes par époque sur un CPU 4 cœurs en `MODE_RAPIDE`
    (davantage sur un portable modeste), moins d'une minute sur GPU.
    """),
    code("""
import copy

from sklearn.utils.class_weight import compute_class_weight

modele = timm.create_model(ARCH, pretrained=True, num_classes=len(CLASSES)).to(DEVICE)
poids = compute_class_weight("balanced", classes=np.arange(len(CLASSES)),
                             y=[CLASSES.index(c) for c in train["classe"]])
critere = nn.CrossEntropyLoss(weight=torch.tensor(poids, dtype=torch.float32, device=DEVICE),
                              label_smoothing=0.1)
optimiseur = torch.optim.AdamW(modele.parameters(), lr=3e-4, weight_decay=0.05)
planning = torch.optim.lr_scheduler.CosineAnnealingLR(optimiseur, T_max=EPOCHS)

historique, meilleur, meilleur_etat = [], -1.0, None
for epoque in range(1, EPOCHS + 1):
    t0 = time.time()
    perte, exact_train = entrainer_une_epoque(modele, dl_train, optimiseur, critere)
    planning.step()
    p_val, y_val = predire(modele, dl_val)
    exact_val = (p_val.argmax(1) == y_val).mean()
    historique.append({"epoque": epoque, "perte": perte, "train": exact_train, "val": exact_val})
    if exact_val > meilleur:
        meilleur, meilleur_etat = exact_val, copy.deepcopy(modele.state_dict())
    print(f"époque {epoque} : perte {perte:.3f}, train {exact_train:.3f}, val {exact_val:.3f} "
          f"({time.time() - t0:.0f} s)")

modele.load_state_dict(meilleur_etat)
p_val, y_val = predire(modele, dl_val)   # probabilités du MEILLEUR modèle, pas de la dernière époque
pd.DataFrame(historique).set_index("epoque")[["train", "val"]].plot(figsize=(5, 3), marker="o")
plt.ylabel("exactitude"); plt.show()
"""),
    md("""
    ❓ Comparez les exactitudes d'entraînement et de validation au fil des époques. Si
    celle d'entraînement est plus basse, qu'est-ce qui peut l'expliquer (augmentations,
    exactitude mesurée pendant que les poids changent) ?

    ## 5. Évaluer correctement

    ### Exercice 5.1 : sur le test

    Calculez les probabilités sur `dl_test`, puis affichez le rapport de classification
    et la matrice de confusion (`ConfusionMatrixDisplay`, vraies classes en lignes,
    prédictions en colonnes).
    """),
    exo(
        """
from sklearn.metrics import ConfusionMatrixDisplay

# p_test, y_test = predire(...)
# print(classification_report(...))
# ConfusionMatrixDisplay.from_predictions(...)
""",
        """
from sklearn.metrics import ConfusionMatrixDisplay

p_test, y_test = predire(modele, dl_test)
print(classification_report(y_test, p_test.argmax(1), target_names=CLASSES, digits=3))
ConfusionMatrixDisplay.from_predictions(y_test, p_test.argmax(1), display_labels=CLASSES,
                                        cmap="Greens", colorbar=False)
plt.title("Test (sans copie du train)"); plt.show()
""",
    ),
    md("""
    ❓ Pour un oléiculteur, quelle erreur coûte le plus cher : une feuille malade déclarée
    saine, ou une feuille saine déclarée malade ? Repérez les cases correspondantes dans
    la matrice.

    ### Exercice 5.2 : savoir dire « je ne sais pas »

    Le modèle renvoie une probabilité par classe. Quand la plus haute (la **confiance**)
    est faible, mieux vaut répondre **« incertain »** et faire vérifier la feuille.

    On trie les images de la plus sûre à la moins sûre, puis on trace la **courbe
    risque-couverture** :
    - la *couverture* est la part des images sur lesquelles le modèle décide ;
    - le *risque* est le taux d'erreur sur ces images (1 − exactitude).

    1. Sur la **validation**, tracez l'exactitude en fonction de la couverture.
    2. Choisissez le seuil de confiance le plus bas qui garde au moins `CIBLE` = 98 %
       d'exactitude : c'est la confiance de la dernière position où l'exactitude cumulée
       atteint la cible (`np.nonzero`). Si la cible n'est jamais atteinte, prenez 1,0.
    3. Appliquez ce seuil au **test** : quelle part d'images est décidée, avec quelle
       exactitude ?
    """),
    exo(
        '''
CIBLE = 0.98

def courbe_risque_couverture(probas, y):
    """Renvoie (couverture, exactitude, seuil), triés par confiance décroissante."""
    ...

# couverture, exactitude, seuils = courbe_risque_couverture(p_val, y_val)
# SEUIL_INCERTAIN = ...
''',
        '''
CIBLE = 0.98

def courbe_risque_couverture(probas, y):
    """Renvoie (couverture, exactitude, seuil), triés par confiance décroissante."""
    confiance = probas.max(1)
    ordre = np.argsort(-confiance)
    juste = (probas.argmax(1) == y)[ordre]
    k = np.arange(1, len(y) + 1)
    return k / len(y), np.cumsum(juste) / k, confiance[ordre]

def seuil_pour(cible, exactitude, seuils):
    ok = np.nonzero(exactitude >= cible)[0]
    return float(seuils[ok.max()]) if len(ok) else 1.0

couverture, exactitude, seuils = courbe_risque_couverture(p_val, y_val)
print(f"exactitude globale de validation : {exactitude[-1]:.3f}")
for c in (0.95, 0.98, 0.99):
    s = seuil_pour(c, exactitude, seuils)
    print(f"cible {c:.2f} : seuil {s:.3f}, validation décidée à {(p_val.max(1) >= s).mean():.1%}")
SEUIL_INCERTAIN = seuil_pour(CIBLE, exactitude, seuils)

plt.plot(couverture, exactitude)
plt.axhline(CIBLE, color="grey", ls="--", lw=1)
plt.xlabel("couverture (part des images décidées)"); plt.ylabel("exactitude sur ces images")
plt.title("Validation : exactitude selon la couverture"); plt.grid(alpha=0.3); plt.show()

decide = p_test.max(1) >= SEUIL_INCERTAIN
print(f"seuil {SEUIL_INCERTAIN:.3f} : test décidé à {decide.mean():.1%}, "
      f"exactitude sur ces images {(p_test.argmax(1) == y_test)[decide].mean():.1%}")
''',
    ),
    md("""
    ❓ Sur le test, l'exactitude des images décidées atteint-elle la cible ? Combien de
    feuilles faudrait-il faire vérifier par un humain ? Ce compromis est-il acceptable pour
    un drone qui survole une oliveraie ? Remarque : la validation a servi deux fois, pour
    choisir l'époque puis le seuil. En quoi cela rend-il la courbe un peu optimiste ?

    ## 6. Le vrai test : des feuilles venues d'ailleurs

    Le test précédent vient des **mêmes** photographes, du même appareil et de la même
    région que l'entraînement. Deux autres jeux, jamais vus, mesurent la
    **généralisation** :

    - **Turquie, autre équipe** (Diker et al. 2023) : `sağlam` (sain) et `hastalıklı`
      (œil de paon), images très allongées (1920 × 540) ;
    - **Pérou** (vallée d'Algarrobal, 2024) : `Healthy` et `Peacock_Spot`, sur fond blanc.

    Ils ne contiennent pas d'acariose. On mesure donc surtout « sain contre malade ». La
    probabilité d'être malade est la somme des probabilités des deux maladies :
    `p_malade = 1 − p(sain)`. Une feuille est déclarée malade si `p_malade ≥ 0,5`.

    ### Exercice 6.1

    Construisez un tableau `externe` (chemin, classe, source) pour les deux jeux, prédisez,
    puis calculez pour chaque source :

    - l'exactitude sain / malade ;
    - le rappel des malades (part des feuilles malades détectées) ;
    - les fausses alertes (part des feuilles saines déclarées malades) ;
    - la part d'images décidées avec `SEUIL_INCERTAIN`.
    """),
    exo(
        """
SOURCES = {
    "Turquie (Diker)": (DATA / "olive_leaf_peacock_diker" / "zeytin", {"sağlam": "sain", "hastalıklı": "oeil_de_paon"}),
    "Pérou": (DATA / "olive_leaf_peacock_peru" / "peacock-spot-detection-in-olive-leaves" / "Olive_PNG_Dataset",
              {"Healthy": "sain", "Peacock_Spot": "oeil_de_paon"}),
}
# externe = pd.DataFrame(...)
# pour chaque source : predire(...), p_malade = 1 - p[:, CLASSES.index("sain")], puis les 4 mesures
""",
        """
SOURCES = {
    "Turquie (Diker)": (DATA / "olive_leaf_peacock_diker" / "zeytin", {"sağlam": "sain", "hastalıklı": "oeil_de_paon"}),
    "Pérou": (DATA / "olive_leaf_peacock_peru" / "peacock-spot-detection-in-olive-leaves" / "Olive_PNG_Dataset",
              {"Healthy": "sain", "Peacock_Spot": "oeil_de_paon"}),
}
lignes = []
for source, (racine_src, correspondance) in SOURCES.items():
    for dossier, classe in correspondance.items():
        for f in sorted((racine_src / dossier).iterdir()):
            if f.suffix.lower() in EXTENSIONS:
                lignes.append({"chemin": f, "classe": classe, "source": source})
externe = pd.DataFrame(lignes)

resultats = []
for source, d in externe.groupby("source"):
    p, y = predire(modele, chargeur(d, tf_eval))
    malade_vrai = y != CLASSES.index("sain")
    malade_predit = 1 - p[:, CLASSES.index("sain")] >= 0.5
    resultats.append({
        "source": source, "images": len(d),
        "exactitude sain/malade": (malade_vrai == malade_predit).mean(),
        "rappel malades": malade_predit[malade_vrai].mean(),
        "fausses alertes": malade_predit[~malade_vrai].mean(),
        "part décidée (seuil)": (p.max(1) >= SEUIL_INCERTAIN).mean(),
    })
    ConfusionMatrixDisplay.from_predictions(
        [CLASSES[i] for i in y], [CLASSES[i] for i in p.argmax(1)], labels=CLASSES,
        cmap="Oranges", colorbar=False)
    plt.title(source); plt.show()
pd.DataFrame(resultats).set_index("source").round(3)
""",
    ),
    md("""
    ❓ Comparez avec le test de la partie 5. D'où peut venir l'écart : appareil photo,
    format et cadrage des images, fond, variété d'olivier, stade de la maladie,
    éclairage ? Le seuil « incertain » choisi sur la validation protège-t-il hors source ?
    Qu'en concluez-vous pour des images prises par drone dans une oliveraie française ?

    ## 7. Où regarde le réseau ? (Grad-CAM)

    Grad-CAM colore les zones de l'image qui ont le plus pesé dans la décision. Si le
    réseau regarde le fond plutôt que les taches, il a appris un raccourci.

    ### Exercice 7.1

    Complétez `__call__`. Le *hook* (fourni) mémorise la sortie de la dernière couche de
    convolution (`modele.conv_head`), puis son gradient lors de la rétropropagation.
    Étapes :

    1. passe avant : `logits = self.modele(x)` ; si `classe` vaut None, prendre la classe
       prédite ;
    2. `self.modele.zero_grad()`, puis rétropropager le score de cette classe :
       `logits[0, classe].backward()` ;
    3. poids de chaque canal = moyenne du gradient sur la hauteur et la largeur
       (`dim=(2, 3)`) ;
    4. carte = somme sur les canaux de poids × activation, dont on ne garde que les valeurs
       positives (ReLU) ;
    5. diviser par le maximum pour obtenir des valeurs entre 0 et 1.
    """),
    exo(
        '''
class GradCAM:
    def __init__(self, modele, couche):
        self.modele, self.activation, self.gradient = modele, None, None
        def memoriser(module, entree, sortie):
            if sortie.requires_grad:  # rien à mémoriser pendant predire() (sans gradient)
                self.activation = sortie
                sortie.register_hook(lambda g: setattr(self, "gradient", g))
        couche.register_forward_hook(memoriser)

    def __call__(self, x, classe=None):
        """x : tenseur (1, 3, H, W). Renvoie (carte numpy h x w dans [0, 1], classe)."""
        ...

cam = GradCAM(modele, modele.conv_head)
''',
        '''
class GradCAM:
    def __init__(self, modele, couche):
        self.modele, self.activation, self.gradient = modele, None, None
        def memoriser(module, entree, sortie):
            if sortie.requires_grad:  # rien à mémoriser pendant predire() (sans gradient)
                self.activation = sortie
                sortie.register_hook(lambda g: setattr(self, "gradient", g))
        couche.register_forward_hook(memoriser)

    def __call__(self, x, classe=None):
        """x : tenseur (1, 3, H, W). Renvoie (carte numpy h x w dans [0, 1], classe)."""
        self.modele.eval()
        logits = self.modele(x.to(DEVICE))
        classe = int(logits.argmax(1)) if classe is None else classe
        self.modele.zero_grad()
        logits[0, classe].backward()
        poids = self.gradient.mean(dim=(2, 3), keepdim=True)
        carte = torch.relu((poids * self.activation).sum(dim=1))[0]
        return (carte / (carte.max() + 1e-8)).detach().cpu().numpy(), classe

cam = GradCAM(modele, modele.conv_head)
''',
    ),
    code("""
# Fourni : affiche l'image, puis la carte Grad-CAM, pour quelques erreurs et réussites du test.
def voir_gradcam(lignes, titre):
    fig, axes = plt.subplots(2, len(lignes), figsize=(2.8 * len(lignes), 5.2), squeeze=False)
    for k, (_, r) in enumerate(lignes.iterrows()):
        im = Image.open(r["chemin"]).convert("RGB")
        carte, c = cam(tf_eval(im).unsqueeze(0))
        vue = np.asarray(T.CenterCrop(IMG_SIZE)(T.Resize(int(IMG_SIZE * 1.15))(au_format(im))))
        chaleur = Image.fromarray(np.uint8(carte * 255)).resize(vue.shape[1::-1], Image.BILINEAR)
        axes[0, k].imshow(vue)
        axes[0, k].set_title(f"vrai : {r['classe']}", fontsize=8)
        axes[1, k].imshow(vue)
        axes[1, k].imshow(np.asarray(chaleur), alpha=0.5, cmap="jet")
        axes[1, k].set_title(f"prédit : {CLASSES[c]}", fontsize=8)
        for ax in axes[:, k]:
            ax.axis("off")
    fig.suptitle(titre); plt.tight_layout(); plt.show()

test_pred = test.assign(predit=[CLASSES[i] for i in p_test.argmax(1)])
erreurs = test_pred[test_pred["classe"] != test_pred["predit"]]
voir_gradcam(erreurs.head(5) if len(erreurs) else test_pred.head(5), "Erreurs du test")
voir_gradcam(test_pred[test_pred["classe"] == test_pred["predit"]].sample(5, random_state=0), "Réussites du test")
"""),
    md("""
    ❓ Le réseau regarde-t-il les taches et les déformations, ou les bords et le fond ?

    ## 8. Sauvegarder et réutiliser le modèle

    On sauvegarde les poids et tout ce qu'il faut pour les réutiliser : architecture,
    classes, taille d'image, seuil « incertain ». C'est ce fichier qui serait embarqué sur
    le drone, après export ONNX.
    """),
    code('''
chemin_modele = OUT / "modele_feuilles.pt"
torch.save({"arch": ARCH, "classes": CLASSES, "img_size": IMG_SIZE,
            "seuil_incertain": SEUIL_INCERTAIN, "state_dict": modele.state_dict()}, chemin_modele)

def diagnostiquer(chemin_image, chemin_modele=chemin_modele):
    """Charge le modèle sauvegardé et renvoie (classe ou 'incertain', probabilités)."""
    ck = torch.load(chemin_modele, map_location="cpu", weights_only=True)
    m = timm.create_model(ck["arch"], pretrained=False, num_classes=len(ck["classes"]))
    m.load_state_dict(ck["state_dict"])
    m.eval()
    x = transformation_eval(ck["img_size"])(Image.open(chemin_image).convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        p = torch.softmax(m(x), dim=1)[0].numpy()
    reponse = ck["classes"][p.argmax()] if p.max() >= ck["seuil_incertain"] else "incertain"
    return reponse, {c: round(float(v), 3) for c, v in zip(ck["classes"], p)}

print(f"modèle : {chemin_modele}\\nseuil « incertain » : {SEUIL_INCERTAIN:.3f}")
for _, r in test.groupby("classe").head(1).iterrows():
    print(r["classe"], "->", diagnostiquer(r["chemin"]))
'''),
    md("""
    Essayez `diagnostiquer` sur une photo de feuille d'olivier prise avec votre téléphone.

    ## 9. Pour aller plus loin

    1. **Modèle binaire sain / malade** : réentraînez avec deux classes, puis comparez le
       rappel des malades sur les jeux du Pérou et de Turquie.
    2. **Adapter au nouveau domaine** : ajoutez 20 images du Pérou à l'entraînement, et
       testez sur le reste. Combien d'images suffisent pour regagner l'exactitude perdue ?
    3. **Un autre réseau** : `convnext_tiny.fb_in22k_ft_in1k` (plus gros, souvent plus
       robuste hors domaine). Le gain vaut-il le temps de calcul ?
    4. **Le projet complet** : la même démarche, outillée et reproductible (configs,
       MLflow, export ONNX), est dans le projet blé :
       `uv run agridrone train -c ble/configs/classification/...` (voir `ble/README.md`
       et `ble/reports/baseline_results.md`).

    ## Compte rendu attendu

    Une à deux pages :
    - le tableau des effectifs ;
    - les doublons et fuites trouvés, et le seuil de quasi-doublon choisi ;
    - la référence contre le réseau ;
    - la matrice de confusion du test ;
    - le seuil « incertain » et son coût ;
    - le tableau hors domaine ;
    - deux cartes Grad-CAM commentées ;
    - vos réponses aux ❓.
    """),
]

# ======================================================================
# TP 2 : parasites dans les pièges (mouche de l'olive)
# ======================================================================

TP2: list[Cell] = [
    md("""
    # TP 2 : détecter et compter la mouche de l'olive dans les pièges

    **Objectif.** La mouche de l'olive (*Bactrocera oleae*) est le principal ravageur des
    oliveraies méditerranéennes. On la surveille avec des pièges McPhail. Le nombre de
    mouches capturées par semaine décide du traitement. Vous allez entraîner un
    **détecteur** (YOLO) qui encadre chaque insecte, distingue femelles, mâles et pyrales,
    puis **compte** les mouches.

    **Différence avec le TP 1.** On ne classe plus une image entière. On localise
    **plusieurs petits objets** dans chaque image, avec une boîte et une classe chacun.

    **Ce que vous allez apprendre.**

    1. Lire des annotations COCO, regarder la taille des objets.
    2. Convertir au format YOLO (exercice de géométrie des boîtes).
    3. Entraîner YOLO11, lire précision, rappel, mAP.
    4. Passer de la détection au **comptage**, la mesure qui compte pour l'agriculteur,
       avec un seuil choisi sur la validation.
    5. Tester sur d'autres pièges (Grèce) : généralisation.

    **Comment travailler.** Enregistrez d'abord ce notebook sous un autre nom. Les
    cellules « À FAIRE » sont à compléter, les ❓ vont dans le compte rendu, le corrigé est
    dans `olivier/tp/corriges/`.

    **Données** (une fois, depuis la racine du projet) :

    ```bash
    uv run agridrone data download olive_fly_smartmcphail olive_fly_dirt_coco olive_fly_digital_mcphail
    ```

    Licence : Ultralytics (YOLO) est sous AGPL-3.0. C'est sans problème pour ce projet
    académique.
    """),
    md("## 0. Mise en route"),
    code(
        SETUP_COMMON
        + """
import json
import shutil
from collections import defaultdict

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

OUT = ROOT / "runs" / "olivier" / "tp2"
OUT.mkdir(parents=True, exist_ok=True)
YOLO_DIR = ROOT / "data" / "olivier" / "processed" / "tp2_mouche"

# Sur CPU, environ 30 s par époque en 640 px (CPU 4 cœurs), soit une demi-heure.
EPOCHS = 60 if MODE_RAPIDE else 80
IMGSZ = 640 if MODE_RAPIDE else 1024    # taille (plus grand côté) des images vues par le réseau
BATCH = 8 if MODE_RAPIDE else 16
DEVICE_YOLO = 0 if DEVICE == "cuda" else DEVICE
print(f"EPOCHS={EPOCHS}, IMGSZ={IMGSZ}")
"""
    ),
    md("""
    ## 1. Les données : SmartMcPhail

    209 photos prises dans des pièges McPhail connectés, en oliveraies commerciales.
    Chaque insecte est encadré et étiqueté `Female`, `Male` (mouche de l'olive) ou
    `Glyphode` (pyrale du jasmin, autre ravageur). L'autrice fournit un découpage
    train / valid / test, et aucune photo ne se trouve dans deux découpages.

    Format d'annotation COCO : un fichier JSON avec la liste des `images`, des
    `annotations` (boîte `bbox = [x, y, largeur, hauteur]` en pixels, coin haut-gauche) et
    des `categories`.
    """),
    code('''
SMART = DATA / "olive_fly_smartmcphail" / "FinalDataset.coco" / "FinalDataset.coco"

def lire_coco(fichier):
    """Une ligne par boîte : image, taille de l'image, classe, boîte COCO."""
    d = json.loads(Path(fichier).read_text(encoding="utf-8"))
    categories = {c["id"]: c["name"] for c in d["categories"]}
    images = {im["id"]: im for im in d["images"]}
    lignes = [{
        "image": images[a["image_id"]]["file_name"],
        "W": images[a["image_id"]]["width"], "H": images[a["image_id"]]["height"],
        "classe": categories[a["category_id"]],
        "x": a["bbox"][0], "y": a["bbox"][1], "w": a["bbox"][2], "h": a["bbox"][3],
    } for a in d["annotations"]]
    return pd.DataFrame(lignes), [im["file_name"] for im in d["images"]]

boites = {}
for split in ("train", "valid", "test"):
    boites[split], _ = lire_coco(SMART / split / "_annotations.coco.json")
    boites[split]["split"] = split
toutes = pd.concat(boites.values(), ignore_index=True)
pd.crosstab(toutes["classe"], toutes["split"], margins=True)
'''),
    md("""
    ### Exercice 1.1 : quelle taille font les insectes ?

    Ajoutez une colonne `taille_rel` = largeur de la boîte / plus grand côté de l'image
    (`max(W, H)` : la plupart des photos sont en portrait). Tracez son histogramme. Puis,
    pour `IMGSZ` = 640, 1024 et 1280, calculez la largeur d'un insecte en pixels (médiane
    et 10e centile) une fois l'image réduite à `IMGSZ`.

    ❓ Un détecteur a du mal en dessous d'environ 10 pixels. Quelle valeur d'`IMGSZ`
    conseillez-vous, et à quel coût de calcul ?
    """),
    exo(
        """
# toutes["taille_rel"] = ...
# toutes["taille_rel"].plot.hist(...)
# for taille in (640, 1024, 1280): px = toutes["taille_rel"] * taille ; print(px.median(), px.quantile(0.1))
""",
        """
toutes["taille_rel"] = toutes["w"] / toutes[["W", "H"]].max(axis=1)
toutes["taille_rel"].plot.hist(bins=40, figsize=(5, 3))
plt.xlabel("largeur de la boîte / plus grand côté de l'image"); plt.show()
for taille in (640, 1024, 1280):
    px = toutes["taille_rel"] * taille
    print(f"IMGSZ={taille} : largeur médiane {px.median():.0f} px, 10e centile {px.quantile(0.1):.0f} px")
""",
    ),
    md("""
    ### Exercice 1.2 : afficher une image avec ses boîtes

    Écrivez `afficher(split, image)`, qui dessine l'image et ses boîtes : un rectangle
    `patches.Rectangle((x, y), w, h)` par boîte, avec une couleur par classe.
    """),
    exo(
        """
COULEURS = {"Female": "#e4572e", "Male": "#17bebb", "Glyphode": "#ffc914"}

def afficher(split, image):
    ...

afficher("train", boites["train"]["image"].iloc[0])
""",
        """
COULEURS = {"Female": "#e4572e", "Male": "#17bebb", "Glyphode": "#ffc914"}

def afficher(split, image):
    fig, ax = plt.subplots(figsize=(6, 8))
    ax.imshow(Image.open(SMART / split / image))
    for _, b in boites[split][boites[split]["image"] == image].iterrows():
        ax.add_patch(patches.Rectangle((b["x"], b["y"]), b["w"], b["h"], fill=False,
                                       lw=1.5, color=COULEURS.get(b["classe"], "white")))
    ax.set_title(image[:40]); ax.axis("off")
    ax.legend(handles=[patches.Patch(color=c, label=k) for k, c in COULEURS.items()], loc="lower right")
    plt.show()

afficher("train", boites["train"]["image"].iloc[0])
""",
    ),
    md("""
    ❓ Comment distinguez-vous une femelle d'un mâle ? (Indice : l'ovipositeur au bout de
    l'abdomen.) Ce détail est-il visible à la résolution de travail du réseau ?

    ## 2. Convertir au format YOLO

    YOLO attend, pour chaque image, un fichier `.txt` avec une ligne par objet :

    ```
    classe x_centre y_centre largeur hauteur
    ```

    Les quatre nombres sont **normalisés** entre 0 et 1 par la taille de l'image. COCO
    donne `x, y` = coin haut-gauche, en pixels.

    ### Exercice 2.1

    Complétez `coco_vers_yolo`. Copiez chaque image dans `<sortie>/images/<split>` et
    écrivez ses étiquettes dans `<sortie>/labels/<split>`, dans un fichier `.txt` **de
    même nom** que l'image (`photo.jpg` → `photo.txt`) : c'est ainsi que YOLO associe
    image et étiquettes. Les `category_id` se traduisent en noms avec `d["categories"]`,
    puis en numéros de classe avec `correspondance`. La catégorie `Gliphode-Male-Female`
    est une super-catégorie vide de Roboflow : ignorez toute catégorie absente de
    `correspondance`.
    """),
    exo(
        """
CLASSES = ["femelle", "male", "pyrale"]
COCO_VERS_ID = {"Female": 0, "Male": 1, "Glyphode": 2}

def coco_vers_yolo(json_coco, dossier_images, split, sortie=YOLO_DIR, correspondance=COCO_VERS_ID):
    d = json.loads(Path(json_coco).read_text(encoding="utf-8"))
    ...  # pour chaque image : lignes "id xc yc w h" normalisées, fichier .txt, copie de l'image

for split_coco, split_yolo in [("train", "train"), ("valid", "val"), ("test", "test")]:
    coco_vers_yolo(SMART / split_coco / "_annotations.coco.json", SMART / split_coco, split_yolo)
""",
        """
CLASSES = ["femelle", "male", "pyrale"]
COCO_VERS_ID = {"Female": 0, "Male": 1, "Glyphode": 2}

def coco_vers_yolo(json_coco, dossier_images, split, sortie=YOLO_DIR, correspondance=COCO_VERS_ID):
    d = json.loads(Path(json_coco).read_text(encoding="utf-8"))
    categories = {c["id"]: c["name"] for c in d["categories"]}
    par_image = defaultdict(list)
    for a in d["annotations"]:
        par_image[a["image_id"]].append(a)
    (sortie / "images" / split).mkdir(parents=True, exist_ok=True)
    (sortie / "labels" / split).mkdir(parents=True, exist_ok=True)
    for im in d["images"]:
        W, H = im["width"], im["height"]
        lignes = []
        for a in par_image[im["id"]]:
            nom = categories[a["category_id"]]
            if nom not in correspondance:
                continue
            x, y, w, h = a["bbox"]
            lignes.append(f"{correspondance[nom]} {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}")
        nom_image = Path(im["file_name"])
        shutil.copy2(dossier_images / nom_image, sortie / "images" / split / nom_image.name)
        (sortie / "labels" / split / f"{nom_image.stem}.txt").write_text("\\n".join(lignes), encoding="utf-8")

for split_coco, split_yolo in [("train", "train"), ("valid", "val"), ("test", "test")]:
    coco_vers_yolo(SMART / split_coco / "_annotations.coco.json", SMART / split_coco, split_yolo)
""",
    ),
    code('''
# Fourni : fichier de description du jeu pour YOLO, et vérification.
def ecrire_yaml(dossier, noms, train="images/train", val="images/val", test="images/test"):
    """Ultralytics exige les clés train et val, même pour une simple évaluation."""
    fichier = dossier / "data.yaml"
    fichier.write_text(f"path: {dossier.as_posix()}\\ntrain: {train}\\nval: {val}\\ntest: {test}\\n"
                       + "names:\\n" + "".join(f"  {i}: {n}\\n" for i, n in enumerate(noms)), encoding="utf-8")
    return fichier

DATA_YAML = ecrire_yaml(YOLO_DIR, CLASSES)
for split in ("train", "val", "test"):
    images = sorted((YOLO_DIR / "images" / split).iterdir())
    sans_txt = [p.name for p in images if not (YOLO_DIR / "labels" / split / f"{p.stem}.txt").exists()]
    n_box = sum(len([l for l in f.read_text().split("\\n") if l]) for f in (YOLO_DIR / "labels" / split).glob("*.txt"))
    print(f"{split:5s} : {len(images)} images, {n_box} boîtes, {len(sans_txt)} image(s) sans fichier d'étiquettes")
print(DATA_YAML.read_text())
'''),
    md("""
    ❓ Vérifiez une conversion à la main. Reprenez la première boîte d'une image, en
    pixels, et retrouvez-la à partir de la ligne YOLO.

    ## 3. Entraîner YOLO11

    `yolo11n.pt` est la plus petite version (2,6 M de paramètres). Elle est pré-entraînée
    sur le jeu d'images COCO (80 classes d'objets du quotidien, sans insecte), celui qui a
    donné son nom au format d'annotation vu en partie 1. Ultralytics s'occupe de la
    boucle, des augmentations (mosaïque de 4 images, couleurs, échelles) et des courbes.
    La mosaïque est coupée pendant les dernières époques (`close_mosaic`), pour finir sur
    des images naturelles.

    Durée indicative : environ 30 s par époque sur un CPU 4 cœurs en 640 px, soit une
    demi-heure en `MODE_RAPIDE`. Sur GPU, 80 époques en 1024 px prennent de l'ordre d'une
    demi-heure (non mesuré ici).
    """),
    code("""
from ultralytics import YOLO

modele = YOLO("yolo11n.pt")   # téléchargé automatiquement la première fois
resultats = modele.train(
    data=str(DATA_YAML), epochs=EPOCHS, imgsz=IMGSZ, batch=BATCH, device=DEVICE_YOLO,
    close_mosaic=min(10, EPOCHS // 5), seed=SEED, workers=NUM_WORKERS,
    project=str(OUT), name="mouche", exist_ok=True, plots=True, verbose=False,
)
MEILLEUR = OUT / "mouche" / "weights" / "best.pt"
courbes = pd.read_csv(OUT / "mouche" / "results.csv")
courbes.plot(x="epoch", y=["metrics/mAP50(B)", "metrics/mAP50-95(B)"], figsize=(5, 3))
plt.title("Validation au fil des époques"); plt.show()
print(MEILLEUR)
"""),
    md("""
    ## 4. Évaluer la détection

    - **IoU** (intersection sur union) : aire commune à la boîte prédite et à la vraie
      boîte, divisée par l'aire de leur réunion (1 = superposition parfaite). Une
      prédiction est juste si son IoU avec une vraie boîte de même classe est ≥ 0,5.
    - **Précision** : part des boîtes prédites qui sont justes. **Rappel** : part des vrais
      insectes trouvés. Ultralytics les donne au seuil de confiance qui maximise le F1.
    - **AP** (*average precision*) : aire sous la courbe précision-rappel, obtenue en
      faisant varier le seuil de confiance. **mAP50** : moyenne des AP des classes, à
      IoU ≥ 0,5. **mAP50-95** : moyenne des mAP pour des IoU exigés de 0,50 à 0,95 ; elle
      récompense les boîtes bien ajustées.

    ### Exercice 4.1

    Évaluez `MEILLEUR` sur le découpage `test`, puis affichez précision, rappel, mAP50 et
    mAP50-95 par classe. Le test ne contient que 7 pyrales : leurs scores sont très
    incertains.
    """),
    exo(
        """
# metriques = YOLO(MEILLEUR).val(data=str(DATA_YAML), split="test", imgsz=IMGSZ, device=DEVICE_YOLO,
#                                plots=True, project=str(OUT), name="test", exist_ok=True)
# metriques.box.p, metriques.box.r, metriques.box.ap50, metriques.box.ap  (un élément par classe)
""",
        """
metriques = YOLO(MEILLEUR).val(data=str(DATA_YAML), split="test", imgsz=IMGSZ, batch=BATCH,
                               device=DEVICE_YOLO, plots=True, project=str(OUT), name="test",
                               exist_ok=True, verbose=False)
tableau = pd.DataFrame({
    "précision": metriques.box.p, "rappel": metriques.box.r,
    "mAP50": metriques.box.ap50, "mAP50-95": metriques.box.ap,
}, index=[metriques.names[int(i)] for i in metriques.box.ap_class_index])
tableau.loc["toutes"] = [metriques.box.mp, metriques.box.mr, metriques.box.map50, metriques.box.map]
tableau.round(3)
""",
    ),
    md("""
    ❓ Ouvrez `runs/olivier/tp2/test/confusion_matrix.png` (à la racine du projet). Attention :
    Ultralytics place les vraies classes en colonnes (axe « True ») et les prédictions en
    lignes, à l'inverse de la matrice du TP 1. Le détecteur confond-il surtout femelles et
    mâles, ou rate-t-il des insectes (ligne « background » : insectes réels non
    détectés) ? Que compte la colonne « background » ?

    ## 5. Du détecteur au comptage

    L'agriculteur n'a pas besoin de boîtes. Il a besoin du **nombre de mouches** par
    piège. On compte les détections de femelles et de mâles dont la confiance dépasse un
    seuil `CONF`. Ce seuil est un réglage : on le choisit sur la **validation**, comme le
    seuil « incertain » du TP 1, puis on l'applique **une seule fois** au test.

    La fonction `detections` (fournie) passe chaque image une fois dans le détecteur, avec
    un seuil très bas, et garde classes et confiances : on peut ensuite compter pour
    n'importe quel seuil sans tout recalculer.
    """),
    code('''
detecteur = YOLO(MEILLEUR)

def detections(images):
    """{nom d'image: (classes, confiances)} pour une liste de chemins d'images."""
    sortie = {}
    for image in images:
        r = detecteur.predict(str(image), conf=0.01, imgsz=IMGSZ, device=DEVICE_YOLO,
                              max_det=1000, verbose=False)[0]
        sortie[Path(image).name] = (r.boxes.cls.cpu().numpy().astype(int), r.boxes.conf.cpu().numpy())
    return sortie

def vrais_comptes(split):
    """{nom d'image: nombre de mouches (femelles + mâles) annotées}."""
    comptes = {}
    for image in (YOLO_DIR / "images" / split).iterdir():
        lignes = (YOLO_DIR / "labels" / split / f"{image.stem}.txt").read_text().split("\\n")
        comptes[image.name] = sum(1 for l in lignes if l and int(l.split()[0]) in (0, 1))
    return comptes

dets = {split: detections(sorted((YOLO_DIR / "images" / split).iterdir())) for split in ("val", "test")}
vrais = {split: vrais_comptes(split) for split in ("val", "test")}
'''),
    md("""
    ### Exercice 5.1

    Écrivez `compter(dets, vrais, conf)`, qui renvoie un tableau image / vrai / prédit (on
    compte les classes 0 et 1 dont la confiance est ≥ `conf`). Sur la **validation**,
    balayez `conf` de 0,05 à 0,6 et retenez celui qui minimise l'erreur absolue moyenne.
    Appliquez-le au **test** : erreur absolue moyenne, totaux, nuage prédit contre vrai.
    """),
    exo(
        """
def compter(dets, vrais, conf):
    ...  # DataFrame avec colonnes image, vrai, predit

# balayage sur dets["val"] -> CONF ; puis comptes_test = compter(dets["test"], vrais["test"], CONF)
""",
        """
def compter(dets, vrais, conf):
    lignes = []
    for nom, (classes, confiances) in dets.items():
        predit = int(((confiances >= conf) & np.isin(classes, (0, 1))).sum())
        lignes.append({"image": nom, "vrai": vrais[nom], "predit": predit})
    return pd.DataFrame(lignes)

balayage = []
for conf in np.arange(0.05, 0.61, 0.05):
    c = compter(dets["val"], vrais["val"], conf)
    balayage.append({"conf": round(conf, 2), "erreur absolue moyenne": (c["predit"] - c["vrai"]).abs().mean(),
                     "total prédit": c["predit"].sum(), "total vrai": c["vrai"].sum()})
balayage = pd.DataFrame(balayage)
display(balayage.round(2))
CONF = float(balayage.loc[balayage["erreur absolue moyenne"].idxmin(), "conf"])

comptes = compter(dets["test"], vrais["test"], CONF)
mae = (comptes["predit"] - comptes["vrai"]).abs().mean()
print(f"CONF = {CONF} (choisi sur la validation) ; test : erreur absolue moyenne {mae:.2f} "
      f"mouche(s) par image ; total vrai {comptes['vrai'].sum()}, total prédit {comptes['predit'].sum()}")
plt.scatter(comptes["vrai"], comptes["predit"], alpha=0.6)
m = comptes[["vrai", "predit"]].max().max()
plt.plot([0, m], [0, m], "k--", lw=1); plt.xlabel("mouches (vrai)"); plt.ylabel("mouches (prédit)")
plt.title("Comptage sur le test"); plt.show()
""",
    ),
    md("""
    ❓ Sur la validation, comment évoluent l'erreur de comptage et le total quand `CONF`
    passe de 0,05 à 0,6 ? Quel seuil retenez-vous pour décider d'un traitement, et que
    donne-t-il sur le test ?

    ## 6. Le vrai test : d'autres pièges

    ### 6.1 DIRT (Grèce, 2018)

    271 images annotées (291 dans l'archive) de pièges McPhail, avec des insectes flottant
    dans le liquide. Les annotations ont une seule classe, `insect`, qui couvre **tous**
    les insectes du piège, y compris d'autres espèces que la mouche de l'olive. On évalue
    donc la capacité à **trouver les insectes**, sans distinguer les classes
    (`single_cls=True`). Pour comparer à armes égales, réévaluez aussi le test
    SmartMcPhail avec `single_cls=True`.

    ### Exercice 6.1

    Convertissez DIRT au format YOLO avec votre `coco_vers_yolo` (annotations dans
    `instances_default.json`, une seule classe : `correspondance={"insect": 0}`, sortie
    dans `data/olivier/processed/tp2_dirt`, découpage `test`). Écrivez son `data.yaml` avec
    `ecrire_yaml`. Évaluez ensuite le détecteur avec `single_cls=True`, sur DIRT et sur le
    test SmartMcPhail.
    """),
    exo(
        """
DIRT = DATA / "olive_fly_dirt_coco" / "DIRT" / "DIRT"
DIRT_YOLO = ROOT / "data" / "olivier" / "processed" / "tp2_dirt"
# coco_vers_yolo(DIRT / "instances_default.json", DIRT, "test", sortie=DIRT_YOLO, correspondance={"insect": 0})
# yaml_dirt = ecrire_yaml(DIRT_YOLO, ["insecte"], train="images/test", val="images/test")
# YOLO(MEILLEUR).val(data=..., split="test", single_cls=True, project=str(OUT), name="dirt", ...)
""",
        """
DIRT = DATA / "olive_fly_dirt_coco" / "DIRT" / "DIRT"
DIRT_YOLO = ROOT / "data" / "olivier" / "processed" / "tp2_dirt"
coco_vers_yolo(DIRT / "instances_default.json", DIRT, "test", sortie=DIRT_YOLO, correspondance={"insect": 0})
yaml_dirt = ecrire_yaml(DIRT_YOLO, ["insecte"], train="images/test", val="images/test")

lignes = []
for nom, yaml, dossier in [("SmartMcPhail (test)", DATA_YAML, "test_single"), ("DIRT", yaml_dirt, "dirt")]:
    m = YOLO(MEILLEUR).val(data=str(yaml), split="test", single_cls=True, imgsz=IMGSZ, batch=BATCH,
                           device=DEVICE_YOLO, project=str(OUT), name=dossier, exist_ok=True, verbose=False)
    lignes.append({"jeu": nom, "précision": m.box.mp, "rappel": m.box.mr, "mAP50": m.box.map50})
pd.DataFrame(lignes).set_index("jeu").round(3)
""",
    ),
    md("""
    ❓ Comparez la mAP50 mono-classe sur SmartMcPhail et sur DIRT. Le score s'effondre-t-il ?
    Regardez `runs/olivier/tp2/dirt/val_batch0_labels.jpg` (vérité) et `val_batch0_pred.jpg`
    (prédictions). Qu'est-ce qui change : liquide, reflets, densité d'insectes, cadrage,
    autres espèces que le modèle n'a jamais vues ?

    ### 6.2 Piège McPhail numérique (Leucade, 2022)

    125 images, sans boîtes, tirées au hasard dans six pièges. Le fichier `counts.csv`
    donne pour chaque image (`image_file`) le nombre total de mouches visibles, recompté à
    l'aveugle par un expert (`expert_count`). C'est exactement la mesure utile sur le
    terrain. Attention à deux colonnes :
    - `pipeline_count` est un incrément journalier : ne la comparez pas à vos comptages ;
    - `density_bin` classe les images selon cet incrément, pas selon le contenu du piège.
      Pour étudier l'erreur selon la densité réelle, faites vos propres tranches
      d'`expert_count` (`pd.cut`).

    ### Exercice 6.2

    Prédisez le nombre de mouches de chaque image, avec le `CONF` choisi sur la
    validation. Comparez-le au comptage de l'expert : erreur absolue moyenne, nuage de
    points, puis erreur par tranche de densité réelle.
    """),
    exo(
        """
DMT = DATA / "olive_fly_digital_mcphail" / "Zenodo_DMT_validation_dataset"
experts = pd.read_csv(DMT / "counts.csv")
# dets_dmt = detections([DMT / "images" / nom for nom in experts["image_file"]])
# compter les classes 0 et 1 au-dessus de CONF, comparer à expert_count
""",
        """
DMT = DATA / "olive_fly_digital_mcphail" / "Zenodo_DMT_validation_dataset"
experts = pd.read_csv(DMT / "counts.csv")
dets_dmt = detections([DMT / "images" / nom for nom in experts["image_file"]])
dmt = compter(dets_dmt, dict(zip(experts["image_file"], experts["expert_count"])), CONF)
dmt = dmt.rename(columns={"vrai": "expert"})
dmt["erreur"] = (dmt["predit"] - dmt["expert"]).abs()
dmt["tranche"] = pd.cut(dmt["expert"], [-1, 0, 5, 15, 40, 10_000], labels=["0", "1-5", "6-15", "16-40", "41+"])
print(f"{len(dmt)} images ; erreur absolue moyenne {dmt['erreur'].mean():.2f} ; "
      f"total expert {dmt['expert'].sum()}, total prédit {dmt['predit'].sum()}")
display(dmt.groupby("tranche", observed=True)[["expert", "predit", "erreur"]].mean().round(1))
plt.scatter(dmt["expert"], dmt["predit"], alpha=0.6)
m = dmt[["expert", "predit"]].max().max()
plt.plot([0, m], [0, m], "k--", lw=1); plt.xlabel("comptage de l'expert"); plt.ylabel("mouches prédites")
plt.title("Leucade : comptage hors source"); plt.show()
""",
    ),
    md("""
    ❓ L'erreur augmente-t-elle avec le nombre de mouches dans le piège ? Pourquoi un piège
    plein (insectes qui se chevauchent, abîmés) est-il plus difficile ? Ce compteur
    suffirait-il pour décider d'un traitement ?

    ## 7. Pour aller plus loin

    1. **Petits objets** : découpez chaque image en tuiles de 640 px qui se recouvrent,
       détectez sur chaque tuile, puis fusionnez les boîtes. La bibliothèque SAHI fait
       cela ; essayez-la sans modifier l'environnement du projet :
       `uv run --with sahi jupyter lab olivier/tp/`. Le rappel augmente-t-il ?
    2. **Plus de données** : ajoutez le jeu croate de Zadar à l'entraînement
       (`uv run agridrone data download olive_fly_zadar`, environ 900 Mo, boîtes Pascal
       VOC). Écrivez la conversion VOC → YOLO.
    3. **Un modèle plus grand** : `yolo11s.pt`. Que gagne-t-on en mAP, et que perd-on en
       vitesse ?
    4. **Vers le drone** : les pièges jaunes englués peuvent être photographiés par un
       drone qui survole l'oliveraie. Quelle résolution au sol faudrait-il pour voir une
       mouche de 5 mm sur au moins 10 pixels ? (`GSD = taille / pixels`)

    ## Compte rendu attendu

    Une à deux pages :
    - effectifs et taille des insectes ;
    - choix d'`IMGSZ` justifié ;
    - tableau des métriques du test ;
    - seuil `CONF` choisi sur la validation et erreur de comptage sur le test ;
    - résultats hors source (DIRT, Leucade) ;
    - vos réponses aux ❓.
    """),
]


def main() -> None:
    (HERE / "corriges").mkdir(exist_ok=True)
    for nom, cells in [("tp1_maladies_feuilles", TP1), ("tp2_parasites_pieges", TP2)]:
        nbformat.write(build(cells, corrige=False), HERE / f"{nom}.ipynb")
        nbformat.write(build(cells, corrige=True), HERE / "corriges" / f"{nom}_corrige.ipynb")
        print(f"{nom} : {len(cells)} cellules")


if __name__ == "__main__":
    main()
