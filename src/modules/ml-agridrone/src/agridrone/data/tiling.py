"""Tuilage d'orthophotos avec chevauchement, et recollage des prédictions.

Les fenêtres couvrent toute l'image : le pas vaut ``tile - overlap`` et la dernière
tuile de chaque ligne/colonne est recalée sur le bord (chevauchement un peu plus
grand plutôt qu'une bande non couverte). Une image plus petite que la tuile donne
une seule fenêtre, complétée par du remplissage (``pad_value``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Window:
    row: int
    col: int
    height: int
    width: int

    @property
    def center(self) -> tuple[float, float]:
        return self.row + self.height / 2, self.col + self.width / 2


def _starts(length: int, tile: int, stride: int) -> list[int]:
    if length <= tile:
        return [0]
    starts = list(range(0, length - tile + 1, stride))
    if starts[-1] != length - tile:
        starts.append(length - tile)
    return starts


def tile_windows(height: int, width: int, tile: int, overlap: int) -> list[Window]:
    """Fenêtres (ligne par ligne) couvrant une image ``height`` × ``width``."""
    if tile <= 0 or not 0 <= overlap < tile:
        raise ValueError(f"tuile {tile} et chevauchement {overlap} incohérents")
    stride = tile - overlap
    return [
        Window(r, c, min(tile, height - r), min(tile, width - c))
        for r in _starts(height, tile, stride)
        for c in _starts(width, tile, stride)
    ]


def extract_tile(array: np.ndarray, window: Window, tile: int, pad_value: float = 0) -> np.ndarray:
    """Extrait une tuile (…, tile, tile) d'un tableau (…, H, W), avec remplissage si besoin."""
    crop = array[
        ..., window.row : window.row + window.height, window.col : window.col + window.width
    ]
    if crop.shape[-2:] == (tile, tile):
        return crop.copy()
    pad = [(0, 0)] * (array.ndim - 2) + [(0, tile - crop.shape[-2]), (0, tile - crop.shape[-1])]
    return np.pad(crop, pad, constant_values=pad_value)


def stitch(
    predictions: list[np.ndarray], windows: list[Window], height: int, width: int
) -> np.ndarray:
    """Recolle des prédictions (K, tile, tile) en moyennant les zones de chevauchement."""
    if len(predictions) != len(windows) or not predictions:
        raise ValueError("une prédiction par fenêtre est attendue")
    channels = predictions[0].shape[0]
    total = np.zeros((channels, height, width), np.float64)
    weight = np.zeros((height, width), np.float64)
    for pred, w in zip(predictions, windows, strict=True):
        total[:, w.row : w.row + w.height, w.col : w.col + w.width] += pred[
            :, : w.height, : w.width
        ]
        weight[w.row : w.row + w.height, w.col : w.col + w.width] += 1
    if (weight == 0).any():
        raise ValueError("des pixels ne sont couverts par aucune fenêtre")
    return (total / weight).astype(np.float32)
