"""Jeux de segmentation multispectrale au format unifié, et tuilage d'orthophotos.

Format de sortie (``data/processed/segmentation/<jeu>/``) :

* ``images/<échantillon>.npy`` : float32 (C, H, W), bandes dans l'ordre de
  ``dataset.json["bands"]`` (noms, voir ``agridrone.data.bands``) ;
* ``masks/<échantillon>.png`` : uint8, une valeur par classe de ``dataset.json["classes"]`` ;
  la valeur 255 marque les pixels à ignorer (sans donnée) ;
* ``index.csv`` : une ligne par échantillon (ensemble, date, pixels par classe…) ;
* ``dataset.json`` : capteur, bandes, classes, licence, nature des valeurs
  (réflectance ou valeurs brutes normalisées).

Les orthophotos GeoTIFF sont découpées par :func:`tile_orthomosaic` en tuiles qui se
chevauchent, géoréférencées (transformée de la fenêtre), avec un découpage spatial
par blocs qui garantit qu'aucun pixel n'est partagé entre deux ensembles.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from pydantic import BaseModel, ConfigDict
from rasterio.windows import Window as RioWindow

from agridrone.data.bands import SensorSpec, load_sensor
from agridrone.data.normalize import BandStats, compute_band_stats
from agridrone.data.raster import read_geotiff, write_geotiff
from agridrone.data.splits import group_split, spatial_split
from agridrone.data.tiling import tile_windows

IGNORE_INDEX = 255


def _save_sample(out_dir: Path, sample: str, image: np.ndarray, mask: np.ndarray) -> None:
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "masks").mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "images" / f"{sample}.npy", image.astype(np.float32, copy=False))
    Image.fromarray(mask.astype(np.uint8)).save(out_dir / "masks" / f"{sample}.png")


def _class_counts(mask: np.ndarray, n_classes: int) -> dict[str, int]:
    counts = np.bincount(mask[mask != IGNORE_INDEX].ravel(), minlength=n_classes)
    return {f"px_{k}": int(v) for k, v in enumerate(counts[:n_classes])}


def remap(mask: np.ndarray, mapping: Mapping[int, int]) -> np.ndarray:
    """Traduit les valeurs brutes d'un masque ; toute valeur non prévue devient 255."""
    lut = np.full(256, IGNORE_INDEX, np.uint8)
    for raw, new in mapping.items():
        lut[raw] = new
    remapped: np.ndarray = lut[mask]
    return remapped


def write_dataset_info(out_dir: Path, info: dict[str, Any]) -> Path:
    path = out_dir / "dataset.json"
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# WeedsGalore (GFZ, DJI P4 Multispectral)
# ---------------------------------------------------------------------------

#: Suffixe de fichier WeedsGalore → nom de bande du projet.
WEEDSGALORE_BAND_FILES = {"blue": "B", "green": "G", "red": "R", "red_edge": "RE", "nir": "NIR"}


def convert_weedsgalore(
    root: Path,
    out_dir: Path,
    sensor: SensorSpec,
    classes: list[str],
    class_map: Mapping[int, int],
    info: dict[str, Any],
) -> pd.DataFrame:
    """Convertit WeedsGalore en conservant son découpage officiel (spatial, par parcelle).

    Les bandes sont des PNG 16 bits de comptes bruts : elles sont ramenées dans [0, 1]
    par division par 65 535 (ce n'est **pas** de la réflectance calibrée).
    """
    rows: list[dict[str, Any]] = []
    for split in ("train", "val", "test"):
        for sample in (root / "splits" / f"{split}.txt").read_text().split():
            date = sample.rsplit("_", 1)[0]
            folder = root / date
            bands = [
                np.asarray(
                    Image.open(folder / "images" / f"{sample}_{WEEDSGALORE_BAND_FILES[b]}.png")
                )
                for b in sensor.band_names
            ]
            image = np.stack(bands).astype(np.float32) / 65535.0
            mask = remap(np.asarray(Image.open(folder / "semantics" / f"{sample}.png")), class_map)
            _save_sample(out_dir, sample, image, mask)
            rows.append(
                {
                    "sample": sample,
                    "split": split,
                    "date": date,
                    "height": image.shape[1],
                    "width": image.shape[2],
                    **_class_counts(mask, len(classes)),
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "index.csv", index=False)
    write_dataset_info(
        out_dir,
        {
            **info,
            "sensor": sensor.name,
            "bands": sensor.band_names,
            "classes": classes,
            "values": "comptes bruts 16 bits / 65535 (non calibrés)",
            "split": "officiel, spatial (par parcelle)",
        },
    )
    return df


# ---------------------------------------------------------------------------
# Patchs .npy déjà découpés (jeu maïs, Turquie)
# ---------------------------------------------------------------------------


def convert_npy_patches(
    image_paths: list[Path],
    mask_for: Mapping[Path, Path],
    out_dir: Path,
    *,
    channel_axis: int,
    keep_channels: list[int],
    alpha_channel: int | None,
    classes: list[str],
    class_map: Mapping[int, int],
    split_of: Mapping[Path, str],
    info: dict[str, Any],
) -> pd.DataFrame:
    """Convertit des patchs .npy (H, W, C) + masques PNG vers le format unifié.

    Les pixels où le canal alpha est nul sont marqués 255 (ignorés) dans le masque.
    """
    rows: list[dict[str, Any]] = []
    for path in image_paths:
        array = np.moveaxis(np.load(path, allow_pickle=False), channel_axis, 0).astype(np.float32)
        mask = remap(np.asarray(Image.open(mask_for[path])), class_map)
        if alpha_channel is not None:
            mask = np.where(array[alpha_channel] > 0, mask, IGNORE_INDEX).astype(np.uint8)
        image = array[keep_channels]
        sample = path.stem
        _save_sample(out_dir, sample, image, mask)
        rows.append(
            {
                "sample": sample,
                "split": split_of[path],
                "height": image.shape[1],
                "width": image.shape[2],
                "valid_fraction": float((mask != IGNORE_INDEX).mean()),
                **_class_counts(mask, len(classes)),
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "index.csv", index=False)
    write_dataset_info(out_dir, {**info, "classes": classes})
    return df


# ---------------------------------------------------------------------------
# Tuilage d'orthophotos GeoTIFF
# ---------------------------------------------------------------------------


def tile_orthomosaic(
    ortho: Path,
    out_dir: Path,
    *,
    tile: int,
    overlap: int,
    block: int,
    fractions: Mapping[str, float],
    seed: int = 0,
    bands: list[int] | None = None,
    alpha_band: int | None = None,
    alpha_threshold: float = 0.5,
    min_valid: float = 0.5,
) -> pd.DataFrame:
    """Découpe une orthophoto en tuiles GeoTIFF qui se chevauchent, avec découpage spatial.

    Validité d'un pixel : masque GDAL (nodata) **et**, si ``alpha_band`` est donné,
    alpha > ``alpha_threshold``. Certaines orthomosaïques ne codent pas leurs zones vides
    en nodata (valeur 0, ou proche de 0, avec un alpha nul) : sans le canal alpha, ces
    zones passeraient pour valides. Les pixels invalides sont écrits en NaN dans les
    tuiles ; les tuiles avec moins de ``min_valid`` de pixels valides sont écartées.
    Chaque tuile garde son géoréférencement.
    """
    with rasterio.open(ortho) as ds:
        height, width = ds.height, ds.width
    windows = tile_windows(height, width, tile, overlap)
    splits = spatial_split(windows, block, fractions, seed=seed)
    rows: list[dict[str, Any]] = []
    for win, split in zip(windows, splits, strict=True):
        if split is None:
            continue
        window = RioWindow(win.col, win.row, win.width, win.height)
        raster = read_geotiff(ortho, bands=bands, window=window)
        if alpha_band is not None:
            alpha = read_geotiff(ortho, bands=[alpha_band], window=window).data[0]
            raster.valid &= alpha > alpha_threshold
        raster.data[:, ~raster.valid] = np.nan
        valid_fraction = float(raster.valid.mean())
        if valid_fraction < min_valid:
            continue
        name = f"{ortho.stem}_r{win.row:06d}_c{win.col:06d}"
        write_geotiff(out_dir / split / f"{name}.tif", raster.data, raster.profile)
        rows.append(
            {
                "tile": name,
                "split": split,
                "row": win.row,
                "col": win.col,
                "height": win.height,
                "width": win.width,
                "valid_fraction": valid_fraction,
            }
        )
    df = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / f"{ortho.stem}_tiles.csv", index=False)
    return df


# ---------------------------------------------------------------------------
# Orchestration (commande `agridrone data prepare-segmentation`)
# ---------------------------------------------------------------------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WeedsGaloreConfig(_Strict):
    source: str
    root: str
    sensor: str
    classes: list[str]
    class_map: dict[int, int]


class MaizeConfig(_Strict):
    source: str
    patch_set: str
    classes: list[str]
    class_map: dict[int, int]
    patch_block: int
    orthomosaics: list[str]
    ortho_bands: list[int]
    ortho_alpha_band: int | None = None
    tile: int
    overlap: int
    block: int
    fractions: dict[str, float]
    seed: int = 0


class SegmentationDataConfig(_Strict):
    weedsgalore: WeedsGaloreConfig
    maize_stress_rust_tr: MaizeConfig


def _train_band_stats(out_dir: Path, df: pd.DataFrame, bands: list[str]) -> BandStats:
    """Statistiques par bande sur l'ensemble d'entraînement uniquement (pixels valides)."""

    def samples() -> Iterator[tuple[np.ndarray, np.ndarray]]:
        for sample in df.loc[df["split"] == "train", "sample"]:
            image = np.load(out_dir / "images" / f"{sample}.npy")
            mask = np.asarray(Image.open(out_dir / "masks" / f"{sample}.png"))
            yield image, mask != IGNORE_INDEX

    stats = compute_band_stats(samples(), bands)
    stats.save(out_dir / "band_stats_train.json")
    return stats


def prepare_segmentation(
    cfg: SegmentationDataConfig, interim_dir: Path, processed_dir: Path, project_root: Path
) -> dict[str, pd.DataFrame]:
    """Prépare WeedsGalore, les patchs maïs et le tuilage des orthomosaïques maïs."""
    results: dict[str, pd.DataFrame] = {}
    wg = cfg.weedsgalore
    sensor = load_sensor(project_root / wg.sensor)
    wg_out = processed_dir / "weedsgalore"
    shutil.rmtree(wg_out, ignore_errors=True)
    results["weedsgalore"] = convert_weedsgalore(
        interim_dir / wg.source / wg.root,
        wg_out,
        sensor,
        wg.classes,
        wg.class_map,
        {"source": wg.source, "license": "CC-BY-4.0", "labels": "annotations manuelles"},
    )
    _train_band_stats(wg_out, results["weedsgalore"], sensor.band_names)

    mz = cfg.maize_stress_rust_tr
    base = interim_dir / mz.source
    patch_dir = base / mz.patch_set
    index = pd.read_csv(patch_dir / "meta" / "patches.csv", encoding="utf-8-sig")
    groups = [
        f"{task}_{x // mz.patch_block}_{y // mz.patch_block}"
        for task, x, y in zip(index["src_task"], index["x0"], index["y0"], strict=True)
    ]
    splits = group_split(groups, mz.fractions, seed=mz.seed)
    paths = [patch_dir / "images" / f"{pid}.npy" for pid in index["id"]]
    mz_out = processed_dir / "maize_patches"
    shutil.rmtree(mz_out, ignore_errors=True)
    results["maize_patches"] = convert_npy_patches(
        paths,
        {p: patch_dir / "masks" / f"{p.stem}.png" for p in paths},
        mz_out,
        channel_axis=-1,
        keep_channels=[0, 1, 2, 3, 4],
        alpha_channel=5,
        classes=mz.classes,
        class_map=mz.class_map,
        split_of=dict(zip(paths, splits, strict=True)),
        info={
            "source": mz.source,
            "license": "CC-BY-4.0",
            "sensor": "dji_p4_multispectral",
            "bands": ["blue", "green", "red", "red_edge", "nir"],
            "values": "normalisées par canal par les auteurs (percentiles 2–98, [0, 1]) ; "
            "pas de réflectance",
            "labels": "PSEUDO-ÉTIQUETTES dérivées d'indices de végétation : ne pas utiliser pour "
            "comparer un modèle à une baseline par indices",
            "split": f"spatial, blocs de {mz.patch_block} px par orthomosaïque",
        },
    )

    tiles_out = processed_dir / "maize_orthotiles"
    shutil.rmtree(tiles_out, ignore_errors=True)
    for rel in mz.orthomosaics:
        ortho = base / rel
        results[f"tiles_{ortho.parent.name}"] = tile_orthomosaic(
            ortho,
            tiles_out / ortho.parent.name,
            tile=mz.tile,
            overlap=mz.overlap,
            block=mz.block,
            fractions=mz.fractions,
            seed=mz.seed,
            bands=mz.ortho_bands,
            alpha_band=mz.ortho_alpha_band,
        )
    return results
