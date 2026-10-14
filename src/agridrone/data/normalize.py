"""Normalisation par bande, avec statistiques calculées sur l'ensemble d'entraînement.

Méthodes (voir aussi ble/reports/data_pipeline.md) :

* ``reflectance`` : données déjà en réflectance calibrée ; on applique seulement le
  facteur d'échelle du capteur et on écrête à [0, 1.5].
* ``percentile`` : par bande, ramène [p_bas, p_haut] vers [0, 1] puis écrête. Utile
  pour des données non calibrées (comptes, 8 bits).
* ``zscore`` : (x - moyenne) / écart-type par bande, appliqué **après** les
  augmentations (albumentations suppose des images float dans [0, 1]).

Les statistiques ne sont jamais calculées sur val/test (fuite d'information).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

Method = Literal["reflectance", "percentile", "zscore"]


class BandStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bands: list[str]
    mean: list[float]
    std: list[float]
    p_low: list[float]
    p_high: list[float]
    percentiles: tuple[float, float]
    n_pixels: int

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path

    @classmethod
    def load(cls, path: str | Path) -> BandStats:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def compute_band_stats(
    samples: Iterable[tuple[np.ndarray, np.ndarray]],
    bands: list[str],
    *,
    percentiles: tuple[float, float] = (2.0, 98.0),
    max_pixels_per_image: int = 20_000,
    seed: int = 0,
) -> BandStats:
    """Statistiques par bande sur des couples (data (C,H,W), valid (H,W)).

    Les percentiles sont estimés sur un sous-échantillon aléatoire de pixels valides
    (au plus ``max_pixels_per_image`` par image) pour borner la mémoire.
    """
    rng = np.random.default_rng(seed)
    picked: list[np.ndarray] = []
    n_total = 0
    for data, valid in samples:
        if data.shape[0] != len(bands):
            raise ValueError(f"{data.shape[0]} canaux, {len(bands)} bandes attendues")
        pixels = data[:, valid].T  # (N, C)
        n_total += len(pixels)
        if len(pixels) > max_pixels_per_image:
            pixels = pixels[rng.choice(len(pixels), max_pixels_per_image, replace=False)]
        picked.append(pixels.astype(np.float64))
    if not picked or n_total == 0:
        raise ValueError("aucun pixel valide pour calculer les statistiques")
    all_pixels = np.concatenate(picked)
    low, high = np.percentile(all_pixels, percentiles, axis=0)
    return BandStats(
        bands=bands,
        mean=all_pixels.mean(axis=0).tolist(),
        std=all_pixels.std(axis=0).tolist(),
        p_low=low.tolist(),
        p_high=high.tolist(),
        percentiles=percentiles,
        n_pixels=n_total,
    )


def normalize(
    data: np.ndarray, method: Method, stats: BandStats | None = None, *, scale: float = 1.0
) -> np.ndarray:
    """Normalise (C, H, W) bande par bande. Renvoie un nouveau tableau float32."""
    x = data.astype(np.float32, copy=True)
    result: np.ndarray
    if method == "reflectance":
        result = np.clip(x * np.float32(scale), 0.0, 1.5)
        return result
    if stats is None:
        raise ValueError(f"la méthode {method!r} nécessite des statistiques d'entraînement")
    if len(stats.bands) != x.shape[0]:
        raise ValueError(f"{x.shape[0]} canaux, statistiques pour {len(stats.bands)} bandes")
    shape = (-1, 1, 1)
    if method == "percentile":
        low = np.asarray(stats.p_low, np.float32).reshape(shape)
        high = np.asarray(stats.p_high, np.float32).reshape(shape)
        result = np.clip((x - low) / np.maximum(high - low, 1e-6), 0.0, 1.0)
        return result
    mean = np.asarray(stats.mean, np.float32).reshape(shape)
    std = np.asarray(stats.std, np.float32).reshape(shape)
    return (x - mean) / np.maximum(std, 1e-6)
