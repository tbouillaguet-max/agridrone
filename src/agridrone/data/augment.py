"""Augmentations réalistes pour la vue drone.

* **RVB** : rotations de 90°, symétries, changement d'échelle (variation d'altitude),
  flou de bougé et de mise au point, variations d'exposition et de gamma,
  compression JPEG (liaison radio).
* **Multispectral** : uniquement des transformations qui **préservent la signature
  spectrale** : géométrie, flous (moyennes spatiales, identiques sur chaque bande) et
  un gain d'exposition **global**, le même facteur sur toutes les bandes, qui laisse
  inchangés les rapports entre bandes et donc NDVI ou NDRE. Ni teinte, ni saturation,
  ni contraste par bande, ni permutation de canaux.

Les images multispectrales doivent être en réflectance (ou ramenées dans [0, 1]) :
albumentations écrête les images float à [0, 1]. La normalisation z-score par bande
s'applique **après** l'augmentation.

Les réductions de taille se font par moyenne de surface (``INTER_AREA``) : une
interpolation bilinéaire qui divise la taille par plus de 2 crée du repliement
(aliasing) qui efface ou déforme les petits symptômes (pustules, taches).
"""

from __future__ import annotations

from typing import Any

import albumentations as A
import numpy as np
from albumentations.core.transforms_interface import ImageOnlyTransform


class GlobalGain(ImageOnlyTransform):  # type: ignore[misc]
    """Multiplie toutes les bandes par un même facteur tiré dans ``gain_range``."""

    def __init__(self, gain_range: tuple[float, float] = (0.8, 1.2), p: float = 0.5) -> None:
        super().__init__(p=p)
        self.gain_range = gain_range

    def get_params(self) -> dict[str, float]:
        return {"gain": self.py_random.uniform(*self.gain_range)}

    def apply(self, img: np.ndarray, gain: float = 1.0, **params: Any) -> np.ndarray:
        return np.clip(img * np.float32(gain), 0.0, 1.0).astype(img.dtype, copy=False)

    def get_transform_init_args_names(self) -> tuple[str, ...]:
        return ("gain_range",)


def rgb_train_transform(size: int, *, seed: int | None = None) -> A.Compose:
    """Classification RVB (image uint8 H×W×3 → H×W×3 redimensionnée à ``size``)."""
    return A.Compose(
        [
            A.RandomResizedCrop(
                size=(size, size), scale=(0.5, 1.0), ratio=(0.8, 1.25), area_for_downscale="image"
            ),
            A.RandomRotate90(p=0.5),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.OneOf([A.MotionBlur(blur_limit=(3, 9)), A.Defocus(radius=(1, 3))], p=0.3),
            A.RandomBrightnessContrast(brightness_limit=0.25, contrast_limit=0.2, p=0.5),
            A.RandomGamma(gamma_limit=(80, 120), p=0.2),
            A.ImageCompression(quality_range=(60, 95), p=0.3),
        ],
        seed=seed,
    )


def rgb_eval_transform(size: int) -> A.Compose:
    """Évaluation, sans hasard : plus petit côté ramené à ``size`` puis recadrage central.

    Pas de déformation des images non carrées (6000×4000 en Éthiopie) ; le recadrage
    carré correspond à l'usage visé (tuiles carrées découpées dans l'image drone).
    """
    return A.Compose(
        [A.SmallestMaxSize(max_size=size, area_for_downscale="image"), A.CenterCrop(size, size)]
    )


def multispectral_train_transform(
    *, scale: tuple[float, float] = (0.8, 1.25), seed: int | None = None
) -> A.Compose:
    """Segmentation N bandes (image float H×W×C dans [0, 1] + masque H×W)."""
    return A.Compose(
        [
            A.RandomRotate90(p=0.5),
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            # Variation d'altitude : interpolation bilinéaire pour l'image, plus proche
            # voisin pour le masque (pas de classe inventée aux frontières).
            A.Affine(scale=scale, p=0.5, border_mode=0, fill=0, fill_mask=0),
            A.OneOf([A.MotionBlur(blur_limit=(3, 7)), A.Defocus(radius=(1, 2))], p=0.2),
            GlobalGain(gain_range=(0.85, 1.15), p=0.5),
        ],
        seed=seed,
    )
