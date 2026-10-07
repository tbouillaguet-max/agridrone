"""Lecture et écriture d'images multibandes au format (C, H, W).

Convention unique dans tout le projet : tableaux ``float32`` de forme (C, H, W),
accompagnés d'un masque ``valid`` (H, W) qui exclut les pixels sans donnée
(bordures d'orthomosaïque, nodata, canal alpha nul).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.windows import Window


@dataclass
class Raster:
    data: np.ndarray  # (C, H, W) float32
    valid: np.ndarray  # (H, W) bool
    profile: dict[str, Any] = field(default_factory=dict)  # crs, transform… (GeoTIFF)

    @property
    def shape(self) -> tuple[int, int, int]:
        c, h, w = self.data.shape
        return c, h, w


def read_geotiff(
    path: str | Path,
    *,
    bands: Sequence[int] | None = None,
    window: Window | None = None,
) -> Raster:
    """Lit un GeoTIFF. ``bands`` : indices 1-based au sens de rasterio (défaut : toutes).

    Les pixels sont invalides si le masque GDAL (nodata ou alpha) les marque comme
    tels dans **une** des bandes lues, ou s'ils ne sont pas finis.
    """
    with rasterio.open(path) as ds:
        indexes = list(bands) if bands is not None else list(range(1, ds.count + 1))
        data = ds.read(indexes, window=window, out_dtype="float32")
        masks = ds.read_masks(indexes, window=window)
        profile = dict(ds.profile)
        if window is not None:
            profile.update(
                height=data.shape[1], width=data.shape[2], transform=ds.window_transform(window)
            )
    valid = (masks > 0).all(axis=0) & np.isfinite(data).all(axis=0)
    return Raster(data=data, valid=valid, profile=profile)


def read_npy(path: str | Path, *, channel_axis: int, alpha_channel: int | None = None) -> Raster:
    """Lit un ``.npy`` multibande et le ramène en (C, H, W).

    Si ``alpha_channel`` est donné (indice dans l'ordre (C, H, W) final), ce canal
    sert de masque de validité puis est retiré des données.
    """
    array = np.load(path, allow_pickle=False)
    if array.ndim != 3:
        raise ValueError(f"{path} : tableau à 3 dimensions attendu, forme {array.shape}")
    data = np.moveaxis(array, channel_axis, 0).astype(np.float32, copy=False)
    valid = np.isfinite(data).all(axis=0)
    if alpha_channel is not None:
        valid &= data[alpha_channel] > 0
        data = np.delete(data, alpha_channel, axis=0)
    return Raster(data=data, valid=valid)


def write_geotiff(path: str | Path, data: np.ndarray, profile: dict[str, Any]) -> Path:
    """Écrit (C, H, W) en GeoTIFF compressé, en conservant crs/transform du profil."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count, height, width = data.shape
    out_profile = {
        "driver": "GTiff",
        "height": height,
        "width": width,
        "count": count,
        "dtype": str(data.dtype),
        "crs": profile.get("crs"),
        "transform": profile.get("transform"),
        "compress": "deflate",
    }
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(data)
    return path
