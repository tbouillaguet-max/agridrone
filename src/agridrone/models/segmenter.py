"""U-Net à N bandes d'entrée (segmentation_models_pytorch) et inférence par tuiles.

L'encodeur vient de timm (préfixe ``tu-``) avec l'étiquette de ses poids, par exemple
``tu-resnet18.a1_in1k`` : poids identifiés sans ambiguïté et licence vérifiable.
Avec N ≠ 3 bandes, smp adapte la première convolution pré-entraînée (poids RVB
recopiés cycliquement puis remis à l'échelle) : le pré-entraînement reste utile pour
les filtres profonds, même si le spectre diffère.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from agridrone.core.device import Precision, autocast_context
from agridrone.data.tiling import extract_tile, stitch, tile_windows

CHECKPOINT_FORMAT = "agridrone.segmenter/1"


def build_unet(
    encoder: str, in_channels: int, num_classes: int, *, pretrained: bool = False
) -> nn.Module:
    """U-Net smp : ``in_channels`` bandes en entrée, ``num_classes`` logits en sortie."""
    import segmentation_models_pytorch as smp

    model: nn.Module = smp.Unet(
        encoder_name=encoder,
        encoder_weights="imagenet" if pretrained else None,
        in_channels=in_channels,
        classes=num_classes,
    )
    return model


@dataclass
class SegmenterCheckpoint:
    encoder: str
    #: Bandes d'entrée, dans l'ordre des canaux du modèle.
    bands: list[str]
    classes: list[str]
    #: Normalisation z-score par bande (statistiques de l'ensemble d'entraînement),
    #: appliquée à des valeurs dans [0, 1].
    mean: list[float]
    std: list[float]
    #: Inférence par tuiles carrées (côté multiple de 32) avec chevauchement.
    tile: int
    overlap: int
    state_dict: dict[str, torch.Tensor]
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_model(cls, model: nn.Module, **fields: Any) -> SegmenterCheckpoint:
        state = {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()}
        return cls(state_dict=state, **fields)

    def build_model(self) -> nn.Module:
        model = build_unet(self.encoder, len(self.bands), len(self.classes))
        model.load_state_dict(self.state_dict)
        model.eval()
        return model

    def normalize(self, image: np.ndarray) -> np.ndarray:
        """(C, H, W) dans [0, 1] → z-score par bande, float32."""
        mean = np.asarray(self.mean, np.float32)[:, None, None]
        std = np.asarray(self.std, np.float32)[:, None, None]
        return (image.astype(np.float32) - mean) / std

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": CHECKPOINT_FORMAT,
            "encoder": self.encoder,
            "bands": list(self.bands),
            "classes": list(self.classes),
            "mean": list(self.mean),
            "std": list(self.std),
            "tile": self.tile,
            "overlap": self.overlap,
            "state_dict": self.state_dict,
            "metadata": self.metadata,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save(payload, tmp)
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> SegmenterCheckpoint:
        payload = torch.load(Path(path), map_location="cpu", weights_only=True)
        found = payload.pop("format", None)
        if found != CHECKPOINT_FORMAT:
            raise ValueError(f"{path} : format {found!r}, attendu {CHECKPOINT_FORMAT!r}")
        return cls(**payload)


@torch.inference_mode()
def predict_tiled(
    model: nn.Module,
    image: np.ndarray,
    *,
    tile: int,
    overlap: int,
    device: torch.device,
    precision: Precision = "fp32",
    batch_size: int = 8,
) -> np.ndarray:
    """Probabilités (K, H, W) d'une image normalisée (C, H, W) de taille quelconque.

    L'image est découpée en tuiles chevauchantes (``tile_windows``), prédites par lots,
    puis recollées en moyennant les chevauchements (``stitch``) : c'est le mode
    d'inférence d'une orthomosaïque, bien plus grande que les tuiles d'entraînement.
    Les bords sont complétés par 0, soit la moyenne de chaque bande après z-score.
    """
    if tile % 32:
        raise ValueError(f"tuile {tile} : un multiple de 32 est requis par le U-Net")
    model.eval()
    _, height, width = image.shape
    windows = tile_windows(height, width, tile, overlap)
    probs: list[np.ndarray] = []
    for start in range(0, len(windows), batch_size):
        batch = np.stack(
            [extract_tile(image, w, tile) for w in windows[start : start + batch_size]]
        )
        with autocast_context(device, precision):
            logits = model(torch.from_numpy(batch).to(device))
        probs.extend(torch.softmax(logits.float(), dim=1).cpu().numpy())
    return stitch(probs, windows, height, width)
