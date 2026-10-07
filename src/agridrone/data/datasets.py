"""Jeux PyTorch construits sur les formats unifiés du chantier 2."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import albumentations as A
import numpy as np
import pandas as pd
import torch
from PIL import Image, ImageOps
from torch.utils.data import Dataset


def load_rgb(path: str | Path, min_size: int | None = None) -> np.ndarray:
    """Image RVB uint8 (H, W, 3), orientation EXIF appliquée.

    Pour un JPEG, ``min_size`` active le décodage réduit (1/2, 1/4 ou 1/8) en gardant
    les deux côtés >= ``min_size`` : une photo 6000×4000 se décode en 750×500, bien
    plus vite. Sans effet sur les autres formats.
    """
    with Image.open(path) as img:
        if min_size is not None and img.format == "JPEG":
            img.draft("RGB", (min_size, min_size))
        oriented = ImageOps.exif_transpose(img)
        return np.asarray(oriented.convert("RGB"))


class ClassificationDataset(Dataset[tuple[torch.Tensor, int]]):
    """Images + étiquettes entières ; renvoie un tenseur (3, H, W) normalisé.

    ``mean`` et ``std`` sont ceux du pré-entraînement du modèle (dans [0, 1]).
    """

    def __init__(
        self,
        files: Sequence[str | Path],
        labels: Sequence[int],
        transform: A.Compose,
        *,
        mean: Sequence[float],
        std: Sequence[float],
        decode_size: int | None = None,
    ) -> None:
        if len(files) != len(labels):
            raise ValueError(f"{len(files)} fichiers pour {len(labels)} étiquettes")
        self.files = [Path(f) for f in files]
        self.labels = [int(label) for label in labels]
        self.transform = transform
        self.decode_size = decode_size
        self._mean = np.asarray(mean, np.float32) * 255.0
        self._std = np.asarray(std, np.float32) * 255.0

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        image = load_rgb(self.files[index], self.decode_size)
        image = self.transform(image=image)["image"]
        x = (image.astype(np.float32) - self._mean) / self._std
        return torch.from_numpy(np.ascontiguousarray(x.transpose(2, 0, 1))), self.labels[index]

    def reseed(self, seed: int) -> None:
        """Appelé par ``seed_worker`` : graine propre à chaque worker et à chaque époque."""
        self.transform.set_random_seed(seed)


def classification_split(
    manifest: pd.DataFrame, root: Path, split: str, classes: Sequence[str]
) -> tuple[list[Path], list[int]]:
    """Fichiers et étiquettes (indices dans ``classes``) d'un ensemble du manifeste.

    ``manifest`` est le ``manifest.csv`` du jeu préparé ; ``root`` son dossier.
    """
    rows = manifest[(manifest["excluded_reason"].fillna("") == "") & (manifest["split"] == split)]
    if rows.empty:
        known = sorted(manifest["split"].dropna().unique())
        raise ValueError(f"ensemble {split!r} vide ou absent du manifeste (connus : {known})")
    unknown = sorted(set(rows["label"]) - set(classes))
    if unknown:
        raise ValueError(f"classes absentes de la config dans l'ensemble {split!r} : {unknown}")
    index = {name: i for i, name in enumerate(classes)}
    return [root / f for f in rows["file"]], [index[label] for label in rows["label"]]


def load_segmentation_sample(data_dir: Path, sample: str) -> tuple[np.ndarray, np.ndarray]:
    """Image (C, H, W) float32 et masque (H, W) uint8 d'un jeu de segmentation préparé
    (``images/<sample>.npy`` et ``masks/<sample>.png``, voir ``data.segmentation``)."""
    image = np.load(data_dir / "images" / f"{sample}.npy").astype(np.float32, copy=False)
    with Image.open(data_dir / "masks" / f"{sample}.png") as m:
        mask = np.asarray(m)
    if image.ndim != 3 or image.shape[1:] != mask.shape:
        raise ValueError(f"{sample} : image {image.shape} et masque {mask.shape} incompatibles")
    return image, mask


class SegmentationDataset(Dataset[tuple[torch.Tensor, torch.Tensor]]):
    """Échantillons N bandes : renvoie (C, h, w) normalisé (z-score) et masque int64.

    ``band_indices`` choisit et ordonne les canaux (bandes nommées résolues en amont).
    Les augmentations s'appliquent aux valeurs dans [0, 1], en H×W×C, **avant** le
    z-score (albumentations écrête les images float à [0, 1]). Avec
    ``samples_per_image`` > 1, chaque image est tirée plusieurs fois par époque, avec
    des recadrages aléatoires différents.
    """

    def __init__(
        self,
        data_dir: Path,
        samples: Sequence[str],
        band_indices: Sequence[int],
        *,
        mean: Sequence[float],
        std: Sequence[float],
        transform: A.Compose | None = None,
        samples_per_image: int = 1,
    ) -> None:
        if len(mean) != len(band_indices) or len(std) != len(band_indices):
            raise ValueError("une moyenne et un écart-type par bande d'entrée")
        self.dir = Path(data_dir)
        self.samples = list(samples)
        self.band_indices = list(band_indices)
        self.transform = transform
        self.samples_per_image = samples_per_image
        self._mean = np.asarray(mean, np.float32)[:, None, None]
        self._std = np.asarray(std, np.float32)[:, None, None]

    def __len__(self) -> int:
        return len(self.samples) * self.samples_per_image

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        image, mask = load_segmentation_sample(self.dir, self.samples[index % len(self.samples)])
        image = image[self.band_indices]
        if self.transform is not None:
            out = self.transform(image=np.ascontiguousarray(image.transpose(1, 2, 0)), mask=mask)
            image, mask = out["image"].transpose(2, 0, 1), out["mask"]
        x = (image - self._mean) / self._std
        return (
            torch.from_numpy(np.ascontiguousarray(x, dtype=np.float32)),
            torch.from_numpy(mask.astype(np.int64)),
        )

    def reseed(self, seed: int) -> None:
        """Appelé par ``seed_worker`` : graine propre à chaque worker et à chaque époque."""
        if self.transform is not None:
            self.transform.set_random_seed(seed)
