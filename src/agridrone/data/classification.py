"""Préparation du jeu de classification des maladies (format « dossiers par classe »).

Étapes :

1. **Inventaire** de chaque source extraite (``data/interim/<source>``) : étiquette
   brute lue dans le nom du dossier parent ou le préfixe du nom de fichier, puis
   traduite vers les classes canoniques par la table ``mapping`` de la config.
2. **Empreintes** : sha1 (doublons exacts) et dHash (quasi-doublons).
3. **Groupes** : composantes connexes de deux relations, toutes sources confondues :
   quasi-doublons (dHash), et même source + même jour de prise de vue (date EXIF,
   quand elle existe). Un groupe n'est jamais coupé entre deux ensembles : c'est le
   découpage « par date » quand la date est connue, « par grappe de quasi-doublons »
   sinon.
4. **Découpage** :
   - sources de rôle ``train`` : découpage par groupes en train / val / test
     (test « intra-source ») ;
   - sources de rôle ``test`` : jeu de test inter-sources ``test_<source>``. Une image
     dont un quasi-doublon figure dans une source d'entraînement en est retirée
     (fuite).
5. **Matérialisation** : liens physiques ``processed/classification/<ensemble>/<classe>/``
   et manifeste CSV (une ligne par image, toutes les décisions tracées ; colonne
   ``file`` = chemin de l'image dans le jeu préparé).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import re
import shutil
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any, Literal

import numpy as np
import pandas as pd
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agridrone.core.config import ConfigError, load_yaml
from agridrone.data.dedup import (
    cluster_ids,
    confirm_pairs,
    dhash,
    dhash256,
    file_sha1,
    near_duplicate_pairs,
)
from agridrone.data.splits import assert_no_group_leakage, group_split

IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"})
IGNORE = "ignore"


class SourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Sous-dossier de ``interim/<source>`` contenant les images.
    root: str = "."
    label_from: Literal["parent_dir", "filename_prefix"] = "parent_dir"
    #: Étiquette brute → classe canonique, ou ``ignore`` pour écarter l'image.
    mapping: dict[str, str]
    role: Literal["train", "test"]
    #: Si défini : deux images de même étiquette dont les numéros de fichier
    #: (dernier entier du nom) diffèrent d'au plus ``sequence_gap`` sont considérées
    #: comme une même série de prises de vue et regroupées.
    sequence_gap: int | None = Field(default=None, ge=1)


class ClassificationDataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classes: list[str]
    fractions: dict[str, float] = Field(
        default_factory=lambda: {"train": 0.7, "val": 0.15, "test": 0.15}
    )
    #: Quasi-doublons : candidats en dHash 64 bits, confirmés en dHash 256 bits.
    near_duplicate_distance: int = 8
    near_duplicate_confirm: int = 12
    seed: int = 0
    sources: dict[str, SourceSpec]

    @model_validator(mode="after")
    def _check_mappings(self) -> ClassificationDataConfig:
        allowed = set(self.classes) | {IGNORE}
        for source_id, spec in self.sources.items():
            unknown = set(spec.mapping.values()) - allowed
            if unknown:
                raise ValueError(f"{source_id} : classes inconnues {sorted(unknown)}")
        return self


def load_classification_config(path: str | Path) -> ClassificationDataConfig:
    try:
        return ClassificationDataConfig.model_validate(load_yaml(path))
    except ValueError as exc:
        raise ConfigError(f"{path} : config de classification invalide\n{exc}") from exc


def raw_label(path: Path, spec: SourceSpec) -> str:
    if spec.label_from == "parent_dir":
        return path.parent.name
    match = re.match(r"[A-Za-z_\- ]+", path.stem)
    return match.group(0).strip(" _-") if match else path.stem


_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 36867
_DATETIME = 306
_MODEL = 272


def _exif_info(img: Image.Image) -> tuple[str, str]:
    """(jour de prise de vue AAAA-MM-JJ, modèle d'appareil), chaînes vides si absents."""
    try:
        exif = img.getexif()
        raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL) or exif.get(_DATETIME) or ""
        model = str(exif.get(_MODEL) or "").strip("\x00 ")
    except Exception:  # EXIF corrompu : on ignore, l'image reste utilisable
        return "", ""
    day = str(raw)[:10].replace(":", "-") if re.match(r"\d{4}:\d{2}:\d{2}", str(raw)) else ""
    return day, model


def _fingerprint(path: str) -> dict[str, Any]:
    with Image.open(path) as img:
        width, height = img.size
        day, model = _exif_info(img)
        img.draft("RGB", (128, 128))  # décodage JPEG réduit : beaucoup plus rapide
        return {
            "width": width,
            "height": height,
            "exif_date": day,
            "camera": model,
            "dhash": dhash(img),
            "dhash256": dhash256(img),
            "sha1": file_sha1(path),
        }


def scan_sources(cfg: ClassificationDataConfig, interim_dir: Path) -> pd.DataFrame:
    """Inventaire de toutes les images des sources configurées."""
    rows: list[dict[str, Any]] = []
    for source_id, spec in cfg.sources.items():
        root = interim_dir / source_id / spec.root
        if not root.is_dir():
            raise FileNotFoundError(
                f"{root} introuvable : lancer `agridrone data download {source_id}`"
            )
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in IMAGE_EXTENSIONS or path.name.startswith("."):
                continue
            label = raw_label(path, spec)
            rows.append(
                {
                    "path": path.relative_to(interim_dir).as_posix(),
                    "source": source_id,
                    "role": spec.role,
                    "raw_label": label,
                    "label": spec.mapping.get(label),
                }
            )
    return pd.DataFrame(rows)


def add_fingerprints(
    df: pd.DataFrame, interim_dir: Path, workers: int | None = None
) -> pd.DataFrame:
    paths = [str(interim_dir / p) for p in df["path"]]
    # « spawn » : portable (macOS, Windows) et sans fork d'un processus multi-thread.
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        prints = list(pool.map(_fingerprint, paths, chunksize=32))
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(prints)], axis=1)


def _sequence_pairs(df: pd.DataFrame, cfg: ClassificationDataConfig) -> list[tuple[int, int, int]]:
    pairs: list[tuple[int, int, int]] = []
    for source_id, spec in cfg.sources.items():
        if spec.sequence_gap is None:
            continue
        sub = df[df["source"] == source_id]
        numbers = sub["path"].str.extract(r"(\d+)\D*$", expand=False)
        sub = sub.assign(_n=pd.to_numeric(numbers, errors="coerce")).dropna(subset=["_n"])
        for _, group in sub.sort_values("_n").groupby("raw_label"):
            idx, nums = group.index.to_list(), group["_n"].to_list()
            pairs.extend(
                (idx[k], idx[k + 1], 0)
                for k in range(len(idx) - 1)
                if nums[k + 1] - nums[k] <= spec.sequence_gap
            )
    return pairs


def assign_splits(df: pd.DataFrame, cfg: ClassificationDataConfig) -> pd.DataFrame:
    """Ajoute les colonnes ``group``, ``split`` et ``excluded_reason``."""
    df = df.reset_index(drop=True).copy()
    df["excluded_reason"] = ""
    df.loc[df["label"].isna(), "excluded_reason"] = "étiquette non prévue dans le mapping"
    df.loc[df["label"] == IGNORE, "excluded_reason"] = "classe ignorée"

    # Doublons exacts : l'occurrence conservée est prise en priorité dans une source
    # d'entraînement, pour ne jamais vider l'entraînement au profit d'un test.
    priority = df.assign(_p=(df["role"] != "train").astype(int)).sort_values("_p", kind="stable")
    exact_idx = priority.index[priority["sha1"].duplicated(keep="first")]
    df.loc[df.index.isin(exact_idx) & (df["excluded_reason"] == ""), "excluded_reason"] = (
        "doublon exact"
    )

    candidates = near_duplicate_pairs(df["dhash"].to_numpy(np.uint64), cfg.near_duplicate_distance)
    pairs = confirm_pairs(candidates, df["dhash256"].tolist(), cfg.near_duplicate_confirm)
    counts = np.zeros(len(df), dtype=np.int64)
    for i, j, _ in pairs:
        counts[i] += 1
        counts[j] += 1
    df["near_duplicates"] = counts
    # Grappes de quasi-doublons visuels (servent aux contrôles de fuite et d'ambiguïté).
    df["dup_group"] = cluster_ids(len(df), pairs)

    kept = df["excluded_reason"] == ""
    train_dups = set(df.loc[kept & (df["role"] == "train"), "dup_group"])
    leak = kept & (df["role"] == "test") & df["dup_group"].isin(train_dups)
    df.loc[leak, "excluded_reason"] = "quasi-doublon d'une image d'entraînement"

    # Dans un jeu de test, une seule image par grappe de quasi-doublons : sinon la même
    # photo compterait plusieurs fois dans les scores.
    kept = df["excluded_reason"] == ""
    repeated = (
        kept & (df["role"] == "test") & df.duplicated(subset=["source", "dup_group"], keep="first")
    )
    df.loc[repeated, "excluded_reason"] = "quasi-doublon dans le même jeu de test"

    # Quasi-doublons étiquetés différemment : ambigus, écartés plutôt que devinés.
    kept = df["excluded_reason"] == ""
    labels_per_dup = df[kept].groupby("dup_group")["label"].nunique()
    ambiguous = set(labels_per_dup[labels_per_dup > 1].index)
    df.loc[kept & df["dup_group"].isin(ambiguous), "excluded_reason"] = (
        "quasi-doublons de classes différentes"
    )

    # Groupes de découpage : quasi-doublons + même source et même jour de prise de vue
    # + séries de fichiers consécutifs (sources où ``sequence_gap`` est défini).
    dated = df[df["exif_date"] != ""]
    for _, members in dated.groupby(["source", "exif_date"]).groups.items():
        first, *rest = list(members)
        pairs.extend((first, other, 0) for other in rest)
    pairs.extend(_sequence_pairs(df, cfg))
    # Liens limités à un même rôle : ajouter un jeu de test ne peut jamais modifier le
    # découpage des sources d'entraînement (une image de test proche de deux images
    # d'entraînement ne fusionne pas leurs groupes). Les fuites entre rôles sont traitées
    # plus haut, par exclusion des quasi-doublons.
    role = df["role"].to_numpy()
    df["group"] = cluster_ids(len(df), [p for p in pairs if role[p[0]] == role[p[1]]])

    df["split"] = ""
    kept = df["excluded_reason"] == ""
    train_mask = kept & (df["role"] == "train")
    df.loc[train_mask, "split"] = group_split(
        df.loc[train_mask, "group"].tolist(), cfg.fractions, seed=cfg.seed
    )
    test_mask = kept & (df["role"] == "test")
    df.loc[test_mask, "split"] = "test_" + df.loc[test_mask, "source"]
    assert_no_group_leakage(df.loc[kept, "group"].tolist(), df.loc[kept, "split"].tolist())
    return df


def processed_files(kept: pd.DataFrame) -> list[str]:
    """Chemin de chaque image gardée dans le jeu préparé : ``<ensemble>/<classe>/<source>__<nom>``.

    Deux images d'une même source peuvent porter le même nom dans des dossiers
    différents : leur nom reçoit alors le début de leur sha1 pour rester unique.
    """
    names = [
        f"{row.split}/{row.label}/{row.source}__{PurePosixPath(row.path).name}"
        for row in kept.itertuples()
    ]
    counts = Counter(names)
    files = []
    for name, sha1 in zip(names, kept["sha1"], strict=True):
        if counts[name] > 1:
            p = PurePosixPath(name)
            name = f"{p.parent}/{p.stem}__{sha1[:8]}{p.suffix}"
        files.append(name)
    if len(set(files)) != len(files):
        raise ValueError("noms de fichiers en double dans le jeu préparé")
    return files


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except FileExistsError:
        raise  # jamais d'écrasement silencieux
    except OSError:  # liens physiques non pris en charge, ou deux volumes différents
        shutil.copy2(src, dst)


def materialize(df: pd.DataFrame, interim_dir: Path, out_dir: Path) -> pd.DataFrame:
    """Crée ``out_dir/<ensemble>/<classe>/<source>__<nom>`` (liens physiques) et le manifeste.

    Renvoie le manifeste écrit : colonne ``file`` = chemin de l'image dans ``out_dir``
    (vide pour les images écartées).
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    df = df.copy()
    kept = df["excluded_reason"] == ""
    df["file"] = ""
    df.loc[kept, "file"] = processed_files(df[kept])
    for row in df[kept].itertuples():
        _link_or_copy(interim_dir / row.path, out_dir / row.file)
    df.to_csv(out_dir / "manifest.csv", index=False)
    summary = summarize(df)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return df


def summarize(df: pd.DataFrame) -> dict[str, Any]:
    kept = df[df["excluded_reason"] == ""]
    return {
        "images_scanned": len(df),
        "images_kept": len(kept),
        "excluded": dict(Counter(df.loc[df["excluded_reason"] != "", "excluded_reason"])),
        "per_split_class": {
            split: dict(Counter(group["label"])) for split, group in kept.groupby("split")
        },
        "per_source_raw_label": {
            source: dict(Counter(group["raw_label"])) for source, group in df.groupby("source")
        },
    }


def prepare_classification(
    cfg: ClassificationDataConfig, interim_dir: Path, out_dir: Path
) -> pd.DataFrame:
    df = scan_sources(cfg, interim_dir)
    if df.empty:
        raise ValueError("aucune image trouvée")
    df = add_fingerprints(df, interim_dir)
    df = assign_splits(df, cfg)
    return materialize(df, interim_dir, out_dir)
