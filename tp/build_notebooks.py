"""Génère les notebooks du TP « maladies et parasites de l'olivier ».

Une seule source pour deux versions : chaque exercice a un squelette (version élève,
``tp/``) et une solution (corrigé, ``tp/corriges/``). Après une modification :

    uv run python tp/build_notebooks.py

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
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb.metadata["language_info"] = {"name": "python"}
    out = []
    for cell in cells:
        if cell[0] == "md":
            out.append(new_markdown_cell(cell[1]))
        elif cell[0] == "code":
            out.append(new_code_cell(cell[1]))
        else:
            src = cell[2] if corrige else cell[1]
            header = "# Corrigé\n" if corrige else "# À FAIRE : complétez cette cellule, puis exécutez-la.\n"
            out.append(new_code_cell(header + src))
    nb.cells = out
    return nb


# ======================================================================
# Code commun : trouver la racine du projet, graines, matériel
# ======================================================================

SETUP_COMMON = '''
import os
import random
import sys
from pathlib import Path

import numpy as np
import torch

# Racine du projet : le dossier qui contient pyproject.toml (le notebook peut être lancé
# depuis tp/ ou tp/corriges/).
ROOT = Path.cwd().resolve()
while not (ROOT / "pyproject.toml").exists() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
DATA = ROOT / "data" / "interim"

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
print(f"Projet : {ROOT}\\nMatériel : {DEVICE}")
'''

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
    6. Tester sur deux jeux d'autres pays (Turquie, Pérou) : le vrai test.
    7. Voir où regarde le réseau (Grad-CAM), sauvegarder et réutiliser le modèle.

    **Comment travailler.** Les cellules marquées « À FAIRE » sont à compléter. Les
    questions ❓ sont à traiter dans votre compte rendu. Le corrigé est dans
    `tp/corriges/`. Ne l'ouvrez qu'après avoir essayé.

    **Données** (à télécharger une fois, depuis la racine du projet, dans un terminal) :

    ```bash
    uv run agridrone data download olive_leaf_uguz_uysal olive_leaf_peacock_diker olive_leaf_peacock_peru
    ```
    """),
    md("## 0. Mise en route"),
    code(SETUP_COMMON + '''
import hashlib
import time

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

OUT = ROOT / "runs" / "tp1"
OUT.mkdir(parents=True, exist_ok=True)

# Réglages : sur CPU, un entraînement court (quelques minutes par époque) ; sur GPU, complet.
MODE_RAPIDE = DEVICE == "cpu"
IMG_SIZE = 192 if MODE_RAPIDE else 224
EPOCHS = 4 if MODE_RAPIDE else 15
BATCH = 32
ARCH = "efficientnet_b0.ra_in1k"   # 5,3 M de paramètres, poids ImageNet
CLASSES = ["sain", "oeil_de_paon", "acariose"]
print(f"MODE_RAPIDE={MODE_RAPIDE}, IMG_SIZE={IMG_SIZE}, EPOCHS={EPOCHS}")
'''),
    md("""
    ## 1. Les données

    Le jeu d'Uğuz et Uysal (Denizli, Turquie, 2019) contient 3 400 photos de feuilles en
    cinq archives. Les auteurs fournissent un découpage « officiel » : des archives
    d'entraînement et une archive de test. Deux dossiers ne portent pas de nom de classe
    (`train3`, `train4`) : ce sont des feuilles atteintes d'œil de paon (vérifié à l'œil).
    """),
    code('''
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
'''),
    md("""
    ### Exercice 1.1 : combien d'images par classe ?

    Affichez un tableau croisé classe × découpage officiel (`pd.crosstab`) et un
    diagramme en barres. Les classes sont-elles équilibrées ?
    """),
    exo('''
# tableau = pd.crosstab(...)
# tableau.plot.bar(...)
''', '''
tableau = pd.crosstab(df["classe"], df["officiel"], margins=True)
display(tableau)
pd.crosstab(df["classe"], df["officiel"]).plot.bar(figsize=(6, 3), rot=0)
plt.ylabel("images")
plt.title("Images par classe et par découpage officiel")
plt.show()
'''),
    md("""
    ### Exercice 1.2 : regarder les images

    Écrivez `montrer(df, n)`, qui affiche `n` images tirées au hasard pour chaque classe.

    ❓ Quels indices visuels distinguent les classes ? Sur quel fond sont prises les
    photos ? Pourquoi est-ce un risque pour un modèle destiné à des images prises au
    champ ou par drone ?
    """),
    exo('''
def montrer(df, n=5, graine=0):
    ...  # une ligne par classe, n images par ligne (plt.subplots, ax.imshow, ax.axis("off"))

montrer(df)
''', '''
def montrer(df, n=5, graine=0):
    classes = sorted(df["classe"].unique())
    fig, axes = plt.subplots(len(classes), n, figsize=(2.6 * n, 2.2 * len(classes)))
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
'''),
    md("""
    ### Exercice 1.3 : les doublons exacts

    Une même photo présente deux fois peut se retrouver à la fois en entraînement et en
    test. Le modèle est alors évalué sur des images qu'il a apprises : c'est une
    **fuite**, qui gonfle les scores.

    Calculez l'empreinte MD5 de chaque fichier (`hashlib.md5(chemin.read_bytes())`),
    puis comptez :

    - les fichiers en double ;
    - les photos présentes **à la fois** dans le train et le test officiels ;
    - les photos rangées dans deux classes différentes.
    """),
    exo('''
# df["md5"] = ...
# nb_doublons = ...
# fuites = ...      # empreintes présentes dans les deux découpages officiels
# conflits = ...    # empreintes associées à deux classes
''', '''
df["md5"] = [hashlib.md5(p.read_bytes()).hexdigest() for p in df["chemin"]]
nb_doublons = len(df) - df["md5"].nunique()
par_empreinte = df.groupby("md5")
fuites = par_empreinte["officiel"].nunique()
fuites = fuites[fuites > 1].index
conflits = par_empreinte["classe"].nunique()
conflits = conflits[conflits > 1].index
print(f"fichiers en double : {nb_doublons}")
print(f"photos à la fois en train et en test : {len(fuites)}")
print(f"photos rangées dans deux classes : {len(conflits)}")
'''),
    md("""
    ### Exercice 1.4 : les quasi-doublons

    Une photo recadrée, réduite ou réenregistrée n'a plus la même empreinte MD5, mais
    c'est la même image. On la repère avec une **empreinte perceptuelle** (*dHash*) :

    1. passer l'image en niveaux de gris, réduite à 17 × 16 pixels ;
    2. comparer chaque pixel à son voisin de droite, ce qui donne 16 × 16 = 256 bits ;
    3. deux images sont quasi identiques si très peu de bits diffèrent (**distance de
       Hamming**).

    Complétez `dhash`. Le reste est fourni :
    - la matrice des distances, calculée par blocs pour ménager la mémoire ;
    - le regroupement : deux images à distance ≤ `SEUIL` vont dans le même **groupe** ;
    - une planche de paires d'images par tranche de distance.

    Ces groupes serviront au découpage : un groupe entier va soit en entraînement, soit en
    validation.
    """),
    exo('''
def dhash(chemin, taille=16):
    """Empreinte perceptuelle : tableau numpy de taille*taille booléens."""
    ...
''', '''
def dhash(chemin, taille=16):
    """Empreinte perceptuelle : tableau numpy de taille*taille booléens."""
    im = Image.open(chemin)
    im.draft("L", (4 * taille, 4 * taille))  # JPEG : décodage réduit, plus rapide
    a = np.asarray(im.convert("L").resize((taille + 1, taille), Image.BILINEAR), dtype=np.int16)
    return (a[:, 1:] > a[:, :-1]).flatten()
'''),
    code('''
# Fourni : distances de Hamming entre toutes les paires, par blocs de 256 images.
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
    fig, axes = plt.subplots(1, 2 * len(tirage), figsize=(2.4 * 2 * len(tirage), 2))
    for m, t in enumerate(tirage):
        for c, idx in enumerate((i[t], j[t])):
            axes[2 * m + c].imshow(Image.open(df["chemin"].iloc[idx]))
            axes[2 * m + c].set_title(f"{df['officiel'].iloc[idx]} / {df['classe'].iloc[idx]}", fontsize=7)
            axes[2 * m + c].axis("off")
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

    ❓ Que se passe-t-il avec un seuil trop large (20, 30) ? Pourquoi les photos de ce jeu,
    toutes prises sur fond uni, piègent-elles une empreinte aussi simple ? Proposez une
    méthode plus robuste, par exemple comparer les sorties d'un réseau pré-entraîné.
    """),
    exo('''
# voir_paires(0, 0) ; voir_paires(1, 4) ; ...
SEUIL = ...   # votre choix
df["groupe"] = grouper(SEUIL)
''', '''
for d_min, d_max in [(0, 0), (1, 4), (5, 9), (10, 20)]:
    voir_paires(d_min, d_max)
# Distance 0 : la même photo réenregistrée. Dès 1 à 4 : des feuilles différentes, posées
# sur le même fond. Un seuil bas suffit : au-delà, les groupes s'enchaînent (« A ressemble
# à B, qui ressemble à C ») et des centaines de feuilles différentes se retrouvent liées.
SEUIL = 3
df["groupe"] = grouper(SEUIL)
melanges = df.groupby("groupe")["officiel"].nunique()
print(f"seuil {SEUIL} : {df['groupe'].nunique()} groupes ; "
      f"{(melanges > 1).sum()} groupes à cheval sur le train et le test officiels")
'''),
    md("""
    ❓ Le MD5 trouvait 24 photos communes au train et au test. Combien en trouvez-vous
    maintenant ? Qu'en concluez-vous sur les scores publiés avec ce découpage officiel ?

    ## 2. Découper sans fuite

    Règles retenues :

    - **test** = le test officiel, **moins** les images dont un quasi-doublon est en
      entraînement (on ne garde que des images jamais vues) ;
    - **validation** = 20 % des groupes du train officiel, tirés par classe
      (`StratifiedGroupKFold`) ; elle sert à choisir l'époque et les seuils ;
    - **entraînement** = le reste, sans doublon exact.
    """),
    exo('''
from sklearn.model_selection import StratifiedGroupKFold

# 1. groupes présents dans le train officiel
# 2. test = test officiel dont le groupe n'est pas dans le train officiel
# 3. train officiel dédoublonné (drop_duplicates sur "md5"), puis StratifiedGroupKFold(n_splits=5)
#    -> une partie pour la validation, le reste pour l'entraînement
# train, val, test = ...
''', '''
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
'''),
    md("""
    ## 3. Une référence sans deep learning

    Avant un réseau de neurones, posez une **référence** simple : si elle fait déjà 95 %,
    le problème est facile, ou biaisé. Ici, chaque image est résumée par l'histogramme de
    ses couleurs (teinte, saturation, valeur), classé par une régression logistique.

    ### Exercice 3.1

    Complétez `histo_hsv`, entraînez la régression sur `train`, puis évaluez-la sur `val`
    (exactitude et rappel par classe).
    """),
    exo('''
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
''', '''
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
'''),
    md("""
    ❓ Quelle classe la couleur seule reconnaît-elle le mieux ? Pourquoi l'acariose
    est-elle plus difficile ?

    ## 4. Un réseau pré-entraîné (*transfer learning*)

    On part d'EfficientNet-B0, entraîné sur ImageNet (1,2 million de photos) : ses
    premières couches savent déjà détecter bords, textures et formes. On remplace sa
    dernière couche par une couche à 3 sorties, puis on ré-entraîne tout le réseau sur
    nos feuilles.

    ### 4.1 Le jeu de données PyTorch et les augmentations (fourni)

    Les augmentations (recadrage, rotations, retournements, couleur) montrent au réseau des
    variantes de chaque photo : il apprend des motifs plutôt que des pixels précis.
    """),
    code('''
import timm
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms as T

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
tf_eval = T.Compose([
    T.Resize(int(IMG_SIZE * 1.15)),
    T.CenterCrop(IMG_SIZE),
    T.ToTensor(),
    T.Normalize(MOYENNE, ECART),
])

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
    """),
    exo('''
def entrainer_une_epoque(modele, chargeur, optimiseur, critere):
    modele.train()
    ...
    return perte_moyenne, exactitude

@torch.no_grad()
def predire(modele, chargeur):
    modele.eval()
    ...
    return probas, etiquettes   # tableaux numpy (n, 3) et (n,)
''', '''
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
'''),
    md("""
    ### 4.3 Entraîner

    - **Poids de classe** : la perte pèse davantage les classes rares.
    - **Lissage des étiquettes** (0,1) : le réseau devient moins sûr de lui, ce qui rend ses
      probabilités plus fiables.
    - **Taux d'apprentissage** en cosinus : il décroît doucement jusqu'à la fin.
    - **On garde la meilleure époque** sur la validation (pas la dernière).

    Durée indicative : environ 1 à 2 minutes par époque sur GPU ; sur CPU, comptez 5 à
    10 minutes par époque en `MODE_RAPIDE`.
    """),
    code('''
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
pd.DataFrame(historique).set_index("epoque")[["train", "val"]].plot(figsize=(5, 3), marker="o")
plt.ylabel("exactitude"); plt.show()
'''),
    md("""
    ❓ L'exactitude d'entraînement est-elle plus haute ou plus basse que celle de
    validation ? Pourquoi les augmentations peuvent-elles inverser l'écart habituel ?

    ## 5. Évaluer correctement

    ### Exercice 5.1 : sur le test

    Calculez les probabilités sur `dl_test`, affichez le rapport de classification
    (précision, rappel, F1 par classe) et la matrice de confusion
    (`ConfusionMatrixDisplay`).
    """),
    exo('''
from sklearn.metrics import ConfusionMatrixDisplay

# p_test, y_test = predire(...)
# print(classification_report(...))
# ConfusionMatrixDisplay.from_predictions(...)
''', '''
from sklearn.metrics import ConfusionMatrixDisplay

p_val, y_val = predire(modele, dl_val)
p_test, y_test = predire(modele, dl_test)
print(classification_report(y_test, p_test.argmax(1), target_names=CLASSES, digits=3))
ConfusionMatrixDisplay.from_predictions(y_test, p_test.argmax(1), display_labels=CLASSES,
                                        cmap="Greens", colorbar=False)
plt.title("Test (sans quasi-doublon du train)"); plt.show()
'''),
    md("""
    ❓ Pour un oléiculteur, quelle erreur coûte le plus cher : une feuille malade déclarée
    saine, ou une feuille saine déclarée malade ? Lisez-la dans la matrice.

    ### Exercice 5.2 : savoir dire « je ne sais pas »

    Le modèle renvoie une probabilité par classe. Quand la plus haute est faible, mieux
    vaut répondre **« incertain »** et faire vérifier la feuille.

    1. Sur la **validation**, tracez l'exactitude en fonction de la part d'images gardées
       (on garde les plus sûres d'abord).
    2. Choisissez le seuil de confiance le plus bas qui garde `CIBLE` = 95 % d'exactitude
       sur la validation.
    3. Appliquez ce seuil au **test** : quelle part d'images est décidée, avec quelle
       exactitude ?
    """),
    exo('''
def courbe_risque_couverture(probas, y):
    """Renvoie (couverture, exactitude, seuil), triés par confiance décroissante."""
    ...

CIBLE = 0.95
# couverture, exactitude, seuils = courbe_risque_couverture(p_val, y_val)
# SEUIL_INCERTAIN = ...
''', '''
def courbe_risque_couverture(probas, y):
    """Renvoie (couverture, exactitude, seuil), triés par confiance décroissante."""
    confiance = probas.max(1)
    ordre = np.argsort(-confiance)
    juste = (probas.argmax(1) == y)[ordre]
    n = np.arange(1, len(y) + 1)
    return n / len(y), np.cumsum(juste) / n, confiance[ordre]

CIBLE = 0.95
couverture, exactitude, seuils = courbe_risque_couverture(p_val, y_val)
ok = np.nonzero(exactitude >= CIBLE)[0]
SEUIL_INCERTAIN = float(seuils[ok.max()]) if len(ok) else 1.0
plt.plot(couverture, exactitude)
plt.xlabel("part des images décidées"); plt.ylabel("exactitude sur ces images")
plt.title("Validation : risque contre couverture"); plt.grid(alpha=0.3); plt.show()

decide = p_test.max(1) >= SEUIL_INCERTAIN
print(f"seuil {SEUIL_INCERTAIN:.3f} : test décidé à {decide.mean():.1%}, "
      f"exactitude sur ces images {(p_test.argmax(1) == y_test)[decide].mean():.1%}")
'''),
    md("""
    ## 6. Le vrai test : des feuilles d'autres pays

    Le test précédent vient des **mêmes** photographes, du même appareil et de la même
    région que l'entraînement. Deux autres jeux, jamais vus, mesurent la
    **généralisation** :

    - **Turquie** (Diker et al. 2023) : `sağlam` (sain) et `hastalıklı` (œil de paon) ;
    - **Pérou** (vallée d'Algarrobal, 2024) : `Healthy` et `Peacock_Spot`, sur fond blanc.

    Ils ne contiennent pas d'acariose. On mesure donc surtout « sain contre malade ».

    ### Exercice 6.1

    Construisez un tableau `externe` (chemin, classe, source) pour les deux jeux, prédisez,
    puis calculez pour chaque source :

    - l'exactitude sain / malade, en comptant comme « malade » toute prédiction autre que
      `sain` ;
    - le rappel des malades (part des feuilles malades détectées) ;
    - les fausses alertes (part des feuilles saines déclarées malades).
    """),
    exo('''
SOURCES = {
    "Turquie (Diker)": (DATA / "olive_leaf_peacock_diker" / "zeytin", {"sağlam": "sain", "hastalıklı": "oeil_de_paon"}),
    "Pérou": (DATA / "olive_leaf_peacock_peru" / "peacock-spot-detection-in-olive-leaves" / "Olive_PNG_Dataset",
              {"Healthy": "sain", "Peacock_Spot": "oeil_de_paon"}),
}
# externe = pd.DataFrame(...)
# pour chaque source : predire(...), puis exactitude sain/malade, rappel malade, fausses alertes
''', '''
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
    malade_predit = p.argmax(1) != CLASSES.index("sain")
    decide = p.max(1) >= SEUIL_INCERTAIN
    resultats.append({
        "source": source, "images": len(d),
        "exactitude sain/malade": (malade_vrai == malade_predit).mean(),
        "rappel malades": malade_predit[malade_vrai].mean(),
        "fausses alertes": malade_predit[~malade_vrai].mean(),
        "part décidée (seuil)": decide.mean(),
    })
    ConfusionMatrixDisplay.from_predictions(
        [CLASSES[i] for i in y], [CLASSES[i] for i in p.argmax(1)], labels=CLASSES,
        cmap="Oranges", colorbar=False)
    plt.title(source); plt.show()
pd.DataFrame(resultats).set_index("source").round(3)
'''),
    md("""
    ❓ Comparez avec le test de la partie 5. D'où peut venir l'écart : appareil photo,
    fond, variété d'olivier, stade de la maladie, éclairage ? Qu'en concluez-vous pour des
    images prises par drone dans une oliveraie française ?

    ## 7. Où regarde le réseau ? (Grad-CAM)

    Grad-CAM colore les zones de l'image qui ont le plus pesé dans la décision. Si le
    réseau regarde le fond plutôt que les taches, il a appris un raccourci.

    ### Exercice 7.1

    Complétez la classe `GradCAM`. Un *hook* mémorise la sortie de la dernière couche de
    convolution (`modele.conv_head`) et son gradient. La carte est la somme des cartes
    d'activation, pondérées par la moyenne de leur gradient, passée dans un ReLU, puis
    normalisée entre 0 et 1.
    """),
    exo('''
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
''', '''
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
'''),
    code('''
# Fourni : affiche l'image, puis la carte Grad-CAM, pour quelques erreurs et réussites du test.
def voir_gradcam(lignes, titre):
    fig, axes = plt.subplots(2, len(lignes), figsize=(2.8 * len(lignes), 5.2))
    for k, (_, r) in enumerate(lignes.iterrows()):
        im = Image.open(r["chemin"]).convert("RGB")
        x = tf_eval(im).unsqueeze(0)
        carte, c = cam(x)
        vue = np.asarray(T.CenterCrop(IMG_SIZE)(T.Resize(int(IMG_SIZE * 1.15))(im)))
        axes[0, k].imshow(vue); axes[0, k].set_title(f"vrai : {r['classe']}", fontsize=8)
        axes[1, k].imshow(vue); axes[1, k].imshow(np.asarray(Image.fromarray(np.uint8(carte * 255)).resize(vue.shape[1::-1], Image.BILINEAR)), alpha=0.5, cmap="jet")
        axes[1, k].set_title(f"prédit : {CLASSES[c]}", fontsize=8)
        for ax in axes[:, k]:
            ax.axis("off")
    fig.suptitle(titre); plt.tight_layout(); plt.show()

test_pred = test.assign(predit=[CLASSES[i] for i in p_test.argmax(1)])
erreurs = test_pred[test_pred["classe"] != test_pred["predit"]]
voir_gradcam(erreurs.head(5) if len(erreurs) else test_pred.head(5), "Erreurs du test")
voir_gradcam(test_pred[test_pred["classe"] == test_pred["predit"]].sample(5, random_state=0), "Réussites du test")
'''),
    md("""
    ❓ Le réseau regarde-t-il les taches et les déformations, ou les bords et le fond ?

    ## 8. Sauvegarder et réutiliser le modèle
    """),
    code('''
chemin_modele = OUT / "modele_feuilles.pt"
torch.save({"arch": ARCH, "classes": CLASSES, "img_size": IMG_SIZE,
            "seuil_incertain": SEUIL_INCERTAIN, "state_dict": modele.state_dict()}, chemin_modele)

def diagnostiquer(chemin_image, chemin_modele=chemin_modele):
    """Charge le modèle sauvegardé et renvoie (classe ou 'incertain', probabilités)."""
    ck = torch.load(chemin_modele, map_location="cpu", weights_only=True)
    m = timm.create_model(ck["arch"], pretrained=False, num_classes=len(ck["classes"]))
    m.load_state_dict(ck["state_dict"]); m.eval()
    x = tf_eval(Image.open(chemin_image).convert("RGB")).unsqueeze(0)
    with torch.no_grad():
        p = torch.softmax(m(x), dim=1)[0].numpy()
    reponse = ck["classes"][p.argmax()] if p.max() >= ck["seuil_incertain"] else "incertain"
    return reponse, dict(zip(ck["classes"], p.round(3)))

print(chemin_modele)
diagnostiquer(test["chemin"].iloc[0])
'''),
    md("""
    ## 9. Pour aller plus loin

    1. **Modèle binaire sain / malade** : réentraînez avec deux classes, puis comparez le
       rappel des malades sur les jeux du Pérou et de Turquie.
    2. **Adapter au nouveau domaine** : ajoutez 20 images du Pérou à l'entraînement, et
       testez sur le reste. Combien d'images suffisent pour regagner l'exactitude perdue ?
    3. **Un autre réseau** : `convnext_tiny.fb_in22k_ft_in1k` (plus gros, souvent plus
       robuste hors domaine). Le gain vaut-il le temps de calcul ?
    4. **Le projet complet** : la même démarche, outillée et reproductible (configs,
       MLflow, export ONNX), est dans `uv run agridrone train -c configs/classification/...`
       (voir le README et `reports/baseline_results.md` pour le blé).

    ## Compte rendu attendu

    Une à deux pages :
    - le tableau des effectifs ;
    - les doublons et fuites trouvés ;
    - la référence contre le réseau ;
    - la matrice de confusion du test ;
    - le seuil « incertain » ;
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
    **plusieurs objets petits** dans chaque image, avec une boîte et une classe chacun.

    **Ce que vous allez apprendre.**

    1. Lire des annotations COCO, regarder la taille des objets.
    2. Convertir au format YOLO (exercice de géométrie des boîtes).
    3. Entraîner YOLO11, lire précision, rappel, mAP.
    4. Passer de la détection au **comptage**, la mesure qui compte pour l'agriculteur.
    5. Tester sur d'autres pièges (Grèce) : généralisation.

    **Données** (une fois, depuis la racine du projet) :

    ```bash
    uv run agridrone data download olive_fly_smartmcphail olive_fly_dirt_coco olive_fly_digital_mcphail
    ```

    Licence : Ultralytics (YOLO) est sous AGPL-3.0. C'est sans problème pour ce projet
    académique.
    """),
    md("## 0. Mise en route"),
    code(SETUP_COMMON + '''
import json
import shutil
from collections import Counter, defaultdict

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

OUT = ROOT / "runs" / "tp2"
OUT.mkdir(parents=True, exist_ok=True)
YOLO_DIR = ROOT / "data" / "processed" / "tp2_mouche"

MODE_RAPIDE = DEVICE == "cpu"
EPOCHS = 10 if MODE_RAPIDE else 80
IMGSZ = 640 if MODE_RAPIDE else 1024    # taille des images vues par le réseau
BATCH = 8 if MODE_RAPIDE else 16
DEVICE_YOLO = 0 if DEVICE == "cuda" else DEVICE
print(f"MODE_RAPIDE={MODE_RAPIDE}, EPOCHS={EPOCHS}, IMGSZ={IMGSZ}")
'''),
    md("""
    ## 1. Les données : SmartMcPhail

    210 photos prises dans des pièges McPhail connectés, en oliveraies commerciales.
    Chaque insecte est encadré et étiqueté `Female`, `Male` (mouche de l'olive) ou
    `Glyphode` (pyrale du jasmin, autre ravageur). L'autrice fournit un découpage
    train / valid / test, et elle a vérifié qu'aucune photo ne se trouve dans deux
    découpages.

    Format COCO : un fichier JSON avec la liste des `images`, des `annotations` (boîte
    `bbox = [x, y, largeur, hauteur]` en pixels, coin haut-gauche) et des `categories`.
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

    Ajoutez une colonne `taille_rel` = largeur de la boîte / largeur de l'image, tracez son
    histogramme, puis calculez la taille médiane d'un insecte en pixels **après**
    redimensionnement de l'image à `IMGSZ` pixels de côté (le plus grand côté).

    ❓ Un détecteur a du mal en dessous d'environ 10 pixels. Quelle valeur d'`IMGSZ`
    conseillez-vous ?
    """),
    exo('''
# toutes["taille_rel"] = ...
# toutes["taille_rel"].plot.hist(...)
# taille_mediane_px = ...
''', '''
toutes["taille_rel"] = toutes["w"] / toutes["W"]
toutes["taille_rel"].plot.hist(bins=40, figsize=(5, 3))
plt.xlabel("largeur de la boîte / largeur de l'image"); plt.show()
for taille in (640, 1024, 1280):
    px = (toutes["w"] / toutes[["W", "H"]].max(axis=1) * taille).median()
    print(f"IMGSZ={taille} : un insecte fait en médiane {px:.0f} px de large")
'''),
    md("""
    ### Exercice 1.2 : afficher une image avec ses boîtes

    Écrivez `afficher(split, image)`, qui dessine l'image et ses boîtes : un rectangle
    `patches.Rectangle((x, y), w, h)` par boîte, avec une couleur par classe.
    """),
    exo('''
COULEURS = {"Female": "#e4572e", "Male": "#17bebb", "Glyphode": "#ffc914"}

def afficher(split, image):
    ...

afficher("train", boites["train"]["image"].iloc[0])
''', '''
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
'''),
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

    Complétez `coco_vers_yolo` : écrivez les étiquettes et copiez les images dans
    `YOLO_DIR/images/<split>` et `YOLO_DIR/labels/<split>`. La catégorie
    `Gliphode-Male-Female` est une super-catégorie vide de Roboflow : ignorez-la.
    """),
    exo('''
CLASSES = ["femelle", "male", "pyrale"]
COCO_VERS_ID = {"Female": 0, "Male": 1, "Glyphode": 2}

def coco_vers_yolo(json_coco, dossier_images, split):
    d = json.loads(Path(json_coco).read_text(encoding="utf-8"))
    ...  # pour chaque image : lignes "id xc yc w h" normalisées, fichier .txt, copie de l'image

for split_coco, split_yolo in [("train", "train"), ("valid", "val"), ("test", "test")]:
    coco_vers_yolo(SMART / split_coco / "_annotations.coco.json", SMART / split_coco, split_yolo)
''', '''
CLASSES = ["femelle", "male", "pyrale"]
COCO_VERS_ID = {"Female": 0, "Male": 1, "Glyphode": 2}

def coco_vers_yolo(json_coco, dossier_images, split):
    d = json.loads(Path(json_coco).read_text(encoding="utf-8"))
    categories = {c["id"]: c["name"] for c in d["categories"]}
    par_image = defaultdict(list)
    for a in d["annotations"]:
        par_image[a["image_id"]].append(a)
    (YOLO_DIR / "images" / split).mkdir(parents=True, exist_ok=True)
    (YOLO_DIR / "labels" / split).mkdir(parents=True, exist_ok=True)
    for im in d["images"]:
        W, H = im["width"], im["height"]
        lignes = []
        for a in par_image[im["id"]]:
            nom = categories[a["category_id"]]
            if nom not in COCO_VERS_ID:
                continue
            x, y, w, h = a["bbox"]
            lignes.append(f"{COCO_VERS_ID[nom]} {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}")
        nom_image = Path(im["file_name"])
        shutil.copy2(dossier_images / nom_image, YOLO_DIR / "images" / split / nom_image.name)
        (YOLO_DIR / "labels" / split / f"{nom_image.stem}.txt").write_text("\\n".join(lignes), encoding="utf-8")

for split_coco, split_yolo in [("train", "train"), ("valid", "val"), ("test", "test")]:
    coco_vers_yolo(SMART / split_coco / "_annotations.coco.json", SMART / split_coco, split_yolo)
'''),
    code('''
# Fourni : fichier de description du jeu pour YOLO, et vérification.
DATA_YAML = YOLO_DIR / "data.yaml"
DATA_YAML.write_text(
    f"path: {YOLO_DIR.as_posix()}\\ntrain: images/train\\nval: images/val\\ntest: images/test\\n"
    + "names:\\n" + "".join(f"  {i}: {n}\\n" for i, n in enumerate(CLASSES)), encoding="utf-8")
for split in ("train", "val", "test"):
    n_img = len(list((YOLO_DIR / "images" / split).iterdir()))
    n_box = sum(len(f.read_text().split("\\n")) for f in (YOLO_DIR / "labels" / split).glob("*.txt") if f.read_text())
    print(f"{split:5s} : {n_img} images, {n_box} boîtes")
print(DATA_YAML.read_text())
'''),
    md("""
    ❓ Vérifiez une conversion à la main. Reprenez la première boîte d'une image, en
    pixels, et retrouvez-la à partir de la ligne YOLO.

    ## 3. Entraîner YOLO11

    `yolo11n.pt` est la plus petite version (2,6 M de paramètres), pré-entraînée sur COCO
    (80 classes d'objets du quotidien). Ultralytics s'occupe de la boucle, des
    augmentations (mosaïque, couleurs, échelles) et des courbes.

    Durée indicative : sur CPU en `MODE_RAPIDE`, quelques minutes par époque ; sur GPU,
    80 époques en 1024 px prennent de l'ordre d'une demi-heure (non mesuré ici).
    """),
    code('''
from ultralytics import YOLO

modele = YOLO("yolo11n.pt")   # téléchargé automatiquement la première fois
resultats = modele.train(
    data=str(DATA_YAML), epochs=EPOCHS, imgsz=IMGSZ, batch=BATCH, device=DEVICE_YOLO,
    seed=SEED, workers=NUM_WORKERS, project=str(OUT), name="mouche", exist_ok=True,
    plots=True, verbose=False,
)
MEILLEUR = OUT / "mouche" / "weights" / "best.pt"
print(MEILLEUR)
'''),
    md("""
    ## 4. Évaluer la détection

    - **Précision** : part des boîtes prédites qui sont de vrais insectes de la bonne
      classe.
    - **Rappel** : part des vrais insectes trouvés.
    - **mAP50** : précision moyenne, une boîte comptant comme juste si elle recouvre la
      vraie à au moins 50 % (IoU ≥ 0,5). **mAP50-95** fait de même avec des recouvrements
      exigés de 50 à 95 %.

    ### Exercice 4.1

    Évaluez `MEILLEUR` sur le découpage `test` (`YOLO(MEILLEUR).val(..., split="test")`),
    puis affichez précision, rappel, mAP50 et mAP50-95 par classe.
    """),
    exo('''
# metriques = YOLO(MEILLEUR).val(data=..., split="test", imgsz=IMGSZ, device=DEVICE_YOLO, plots=True, ...)
# metriques.box.p, metriques.box.r, metriques.box.ap50, metriques.box.ap  (un élément par classe)
''', '''
metriques = YOLO(MEILLEUR).val(data=str(DATA_YAML), split="test", imgsz=IMGSZ, batch=BATCH,
                               device=DEVICE_YOLO, plots=True, project=str(OUT), name="test",
                               exist_ok=True, verbose=False)
tableau = pd.DataFrame({
    "précision": metriques.box.p, "rappel": metriques.box.r,
    "mAP50": metriques.box.ap50, "mAP50-95": metriques.box.ap,
}, index=[metriques.names[int(i)] for i in metriques.box.ap_class_index]).round(3)
tableau.loc["toutes"] = [metriques.box.mp, metriques.box.mr, metriques.box.map50, metriques.box.map]
tableau.round(3)
'''),
    md("""
    ❓ Ouvrez `runs/tp2/test/confusion_matrix.png`. Le détecteur confond-il surtout
    femelles et mâles, ou rate-t-il des insectes (colonne « background ») ?

    ## 5. Du détecteur au comptage

    L'agriculteur n'a pas besoin de boîtes. Il a besoin du **nombre de mouches** par
    piège. On compte les détections de femelles et de mâles au-dessus d'un seuil de
    confiance, puis on compare au vrai nombre.

    ### Exercice 5.1

    Pour chaque image du test, comptez les mouches prédites (classes 0 et 1, confiance ≥
    `CONF`) et les vraies (fichiers d'étiquettes). Calculez l'erreur absolue moyenne et
    tracez prédit contre vrai.
    """),
    exo('''
CONF = 0.25
# detecteur = YOLO(MEILLEUR)
# pour chaque image de YOLO_DIR/images/test : detecteur.predict(image, conf=CONF, imgsz=IMGSZ, verbose=False)
# r.boxes.cls -> classes prédites ; vraies classes : premier nombre de chaque ligne du .txt
''', '''
CONF = 0.25
detecteur = YOLO(MEILLEUR)
comptes = []
for image in sorted((YOLO_DIR / "images" / "test").iterdir()):
    r = detecteur.predict(str(image), conf=CONF, imgsz=IMGSZ, device=DEVICE_YOLO, verbose=False)[0]
    predit = int(sum(int(c) in (0, 1) for c in r.boxes.cls.tolist()))
    etiquettes = (YOLO_DIR / "labels" / "test" / f"{image.stem}.txt").read_text().split("\\n")
    vrai = sum(1 for l in etiquettes if l and int(l.split()[0]) in (0, 1))
    comptes.append({"image": image.name, "vrai": vrai, "predit": predit})
comptes = pd.DataFrame(comptes)
mae = (comptes["predit"] - comptes["vrai"]).abs().mean()
print(f"erreur absolue moyenne : {mae:.2f} mouche(s) par image ; "
      f"total vrai {comptes['vrai'].sum()}, total prédit {comptes['predit'].sum()}")
plt.scatter(comptes["vrai"], comptes["predit"], alpha=0.6)
m = comptes[["vrai", "predit"]].max().max()
plt.plot([0, m], [0, m], "k--", lw=1); plt.xlabel("mouches (vrai)"); plt.ylabel("mouches (prédit)")
plt.title("Comptage sur le test"); plt.show()
'''),
    md("""
    ❓ Faites varier `CONF` (0,1 ; 0,25 ; 0,5). Comment évoluent l'erreur de comptage et le
    total ? Quel seuil choisiriez-vous pour décider d'un traitement ?

    ## 6. Le vrai test : d'autres pièges

    ### 6.1 DIRT (Grèce, 2018)

    291 images de pièges McPhail, avec des insectes flottant dans le liquide. Tous sont
    annotés en polygones, sous une seule classe `insect`. On évalue donc la capacité à
    **trouver les insectes**, sans distinguer les classes (`single_cls=True`).

    ### Exercice 6.1

    Convertissez DIRT au format YOLO, avec une seule classe et un découpage `test`
    seulement. Les annotations COCO contiennent aussi `bbox` : utilisez-la. Évaluez
    ensuite le détecteur avec `single_cls=True`.
    """),
    exo('''
DIRT = DATA / "olive_fly_dirt_coco" / "DIRT" / "DIRT"
DIRT_YOLO = ROOT / "data" / "processed" / "tp2_dirt"
# même conversion que coco_vers_yolo, mais avec une seule classe (0) ; puis data.yaml (val et test = images/test)
# metriques_dirt = YOLO(MEILLEUR).val(data=..., split="test", single_cls=True, ...)
''', '''
DIRT = DATA / "olive_fly_dirt_coco" / "DIRT" / "DIRT"
DIRT_YOLO = ROOT / "data" / "processed" / "tp2_dirt"
d = json.loads((DIRT / "instances_default.json").read_text(encoding="utf-8"))
par_image = defaultdict(list)
for a in d["annotations"]:
    par_image[a["image_id"]].append(a)
(DIRT_YOLO / "images" / "test").mkdir(parents=True, exist_ok=True)
(DIRT_YOLO / "labels" / "test").mkdir(parents=True, exist_ok=True)
for im in d["images"]:
    W, H = im["width"], im["height"]
    lignes = [f"0 {(x + w / 2) / W:.6f} {(y + h / 2) / H:.6f} {w / W:.6f} {h / H:.6f}"
              for x, y, w, h in (a["bbox"] for a in par_image[im["id"]])]
    shutil.copy2(DIRT / im["file_name"], DIRT_YOLO / "images" / "test" / Path(im["file_name"]).name)
    (DIRT_YOLO / "labels" / "test" / f"{Path(im['file_name']).stem}.txt").write_text("\\n".join(lignes), encoding="utf-8")
yaml_dirt = DIRT_YOLO / "data.yaml"
yaml_dirt.write_text(f"path: {DIRT_YOLO.as_posix()}\\ntrain: images/test\\nval: images/test\\ntest: images/test\\n"
                     "names:\\n  0: insecte\\n", encoding="utf-8")

metriques_dirt = YOLO(MEILLEUR).val(data=str(yaml_dirt), split="test", single_cls=True, imgsz=IMGSZ,
                                    batch=BATCH, device=DEVICE_YOLO, project=str(OUT), name="dirt",
                                    exist_ok=True, verbose=False)
print(f"DIRT : précision {metriques_dirt.box.mp:.3f}, rappel {metriques_dirt.box.mr:.3f}, "
      f"mAP50 {metriques_dirt.box.map50:.3f}")
'''),
    md("""
    ❓ Le score s'effondre-t-il ? Regardez quelques images DIRT. Qu'est-ce qui change :
    liquide, reflets, densité d'insectes, cadrage ?

    ### 6.2 Piège McPhail numérique (Leucade, 2022)

    125 images, sans boîtes, tirées au hasard dans six pièges et cinq niveaux de capture.
    Le fichier `counts.csv` donne pour chaque image (`image_file`) le nombre total de
    mouches visibles, recompté à l'aveugle par un expert (`expert_count`). C'est
    exactement la mesure utile au terrain. La colonne `pipeline_count` est un incrément
    journalier : ne pas la comparer à vos comptages.

    ### Exercice 6.2

    Prédisez le nombre de mouches de chaque image et comparez-le au comptage de l'expert :
    erreur absolue moyenne, nuage de points, puis erreur par niveau de capture
    (`density_bin`).
    """),
    exo('''
DMT = DATA / "olive_fly_digital_mcphail" / "Zenodo_DMT_validation_dataset"
experts = pd.read_csv(DMT / "counts.csv")
# pour chaque ligne : DMT / "images" / image_file -> detecteur.predict(...) -> nombre de mouches
# comparez à expert_count
''', '''
DMT = DATA / "olive_fly_digital_mcphail" / "Zenodo_DMT_validation_dataset"
experts = pd.read_csv(DMT / "counts.csv")
predits = []
for nom in experts["image_file"]:
    res = detecteur.predict(str(DMT / "images" / nom), conf=CONF, imgsz=IMGSZ,
                            device=DEVICE_YOLO, verbose=False)[0]
    predits.append(int(sum(int(c) in (0, 1) for c in res.boxes.cls.tolist())))
dmt = experts.assign(predit=predits).rename(columns={"expert_count": "expert"})
dmt["erreur"] = (dmt["predit"] - dmt["expert"]).abs()
print(f"{len(dmt)} images ; erreur absolue moyenne {dmt['erreur'].mean():.2f}")
display(dmt.groupby("density_bin")[["expert", "predit", "erreur"]].mean().round(1))
plt.scatter(dmt["expert"], dmt["predit"], alpha=0.6)
m = dmt[["expert", "predit"]].max().max()
plt.plot([0, m], [0, m], "k--", lw=1); plt.xlabel("comptage de l'expert"); plt.ylabel("mouches prédites")
plt.title("Leucade : comptage hors source"); plt.show()
'''),
    md("""
    ## 7. Pour aller plus loin

    1. **Petits objets** : découpez chaque image en tuiles de 640 px qui se recouvrent,
       détectez sur chaque tuile, puis fusionnez les boîtes. La bibliothèque SAHI fait
       cela : `uv pip install sahi`. Le rappel augmente-t-il ?
    2. **Plus de données** : ajoutez le jeu croate de Zadar (`olive_fly_zadar`, boîtes
       Pascal VOC) à l'entraînement. Écrivez la conversion VOC → YOLO.
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
    - erreur de comptage et seuil choisi ;
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
