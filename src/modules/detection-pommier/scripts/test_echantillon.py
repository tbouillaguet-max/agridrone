"""Test local du notebook 01 sur un petit échantillon, avec un FAUX FGVC8 qui contient des pièges :
- 4 feuilles saines d'AppleLeaf9 agrandies en 4000 px  → doivent être détectées comme doublons (une seule copie gardée) ;
- 1 feuille MALADE d'AppleLeaf9 étiquetée « healthy »  → conflit d'étiquettes, mise en quarantaine ;
- 1 image PlantDoc recopiée                            → retirée du test externe (le test externe reste indépendant) ;
- 8 images uniques, 2 lignes « scab » (ignorées), 1 fichier absent.

Usage (depuis apple-detection) :
    python scripts/test_echantillon.py <dossier_echantillon_raw> <dossier_de_travail>
<dossier_echantillon_raw> contient appleleaf9/, plantdoc_apple/, gymnsa/ (même structure que raw/, quelques images suffisent).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageFilter

raw, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
fg = work / "fgvc8" / "train_images"
fg.mkdir(parents=True, exist_ok=True)
rows = []
health = sorted((raw / "appleleaf9" / "Health").iterdir())
for i, f in enumerate(health[:4]):
    Image.open(f).resize((4000, 2667), Image.LANCZOS).save(fg / f"dupH{i}.jpg", quality=92)
    rows.append((f"dupH{i}.jpg", "healthy"))
scab = sorted((raw / "appleleaf9" / "Scab").iterdir())[0]
Image.open(scab).resize((4000, 2667)).save(fg / "conflit.jpg", quality=92)
rows.append(("conflit.jpg", "healthy"))
pd0 = sorted((raw / "plantdoc_apple" / "train" / "Apple leaf").iterdir())[0]
Image.open(pd0).convert("RGB").save(fg / "plantdoc_copy.jpg", quality=95)
rows.append(("plantdoc_copy.jpg", "healthy"))
rng = np.random.default_rng(0)
for i in range(8):
    a = (rng.random((334, 500, 3)) * 255).astype(np.uint8)
    Image.fromarray(a).filter(ImageFilter.GaussianBlur(3)).resize((4000, 2672)).save(fg / f"uniq{i}.jpg", quality=92)
    rows.append((f"uniq{i}.jpg", "healthy"))
rows += [("s1.jpg", "scab"), ("s2.jpg", "scab frog_eye_leaf_spot"), ("absent.jpg", "healthy")]
pd.DataFrame(rows, columns=["image", "labels"]).to_csv(work / "fgvc8" / "train.csv", index=False)

src = (Path(__file__).parent.parent / "notebooks" / "01_preparation_donnees.py").read_text(encoding="utf-8")
src = re.sub(r'^RUN_MODE = "inventaire"', 'RUN_MODE = "complet"', src, count=1, flags=re.M)
src = re.sub(r"^DOWNLOAD = True", "DOWNLOAD = False", src, count=1, flags=re.M)
local = (f"LOCAL_DIRS = dict(appleleaf9={str(raw / 'appleleaf9')!r}, fgvc8={str(work / 'fgvc8')!r}, "
         f"plantdoc={str(raw / 'plantdoc_apple')!r}, gymnsa={str(raw / 'gymnsa')!r})")
src = re.sub(r"^LOCAL_DIRS = dict\(.*\)$", lambda m: local, src, count=1, flags=re.M)
(work / "run_test.py").write_text(src, encoding="utf-8")
out = subprocess.run([sys.executable, "-I", "run_test.py"], cwd=work, capture_output=True, text=True)
print(out.stdout[-4000:], out.stderr[-2000:])
q = pd.read_csv(work / "apple_prep" / "quarantaine.csv")
m = pd.read_csv(work / "apple_prep" / "manifest.csv")
assert (q["reason"] == "conflit d'étiquettes entre doublons").sum() == 2, "le conflit n'a pas été détecté"
assert (q["reason"] == "doublon (copie écartée)").sum() >= 5, "doublons non détectés"
assert not ((m["source"] == "plantdoc") & (m["split"] != "test_externe")).any()
assert not (m["rel"] == "plantdoc_copy.jpg").any() or \
    not (m.loc[m["source"] == "plantdoc", "rel"].str.endswith(pd0.name)).any(), "copie PlantDoc présente deux fois"
print("TEST OK")
