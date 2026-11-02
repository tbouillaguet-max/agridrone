"""Classifieur d'images timm (transfer learning) et format de checkpoint.

Le checkpoint est un dictionnaire de types simples, lisible avec
``torch.load(weights_only=True)`` (aucune exécution de code au chargement) :
architecture, classes, prétraitement, règle de décision et poids. Il suffit à
reconstruire le modèle pour l'évaluation ou l'export ONNX, sans la config du run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import torch
from torch import nn

CHECKPOINT_FORMAT = "agridrone.classifier/1"


def build_classifier(
    arch: str,
    num_classes: int,
    *,
    pretrained: bool = False,
    drop_rate: float = 0.0,
    drop_path_rate: float = 0.0,
) -> nn.Module:
    """Modèle timm avec une tête neuve à ``num_classes`` sorties.

    ``arch`` inclut l'étiquette des poids (``efficientnet_b0.ra_in1k``) : les poids
    pré-entraînés sont ainsi identifiés sans ambiguïté (et leur licence vérifiable).
    """
    import timm

    model: nn.Module = timm.create_model(
        arch,
        pretrained=pretrained,
        num_classes=num_classes,
        drop_rate=drop_rate,
        drop_path_rate=drop_path_rate,
    )
    return model


def normalization(model: nn.Module) -> tuple[list[float], list[float]]:
    """Moyenne et écart-type (dans [0, 1]) du pré-entraînement du modèle."""
    import timm

    cfg = timm.data.resolve_model_data_config(model)
    return [float(v) for v in cfg["mean"]], [float(v) for v in cfg["std"]]


@dataclass
class ClassifierCheckpoint:
    arch: str
    classes: list[str]
    input_size: int
    mean: list[float]
    std: list[float]
    state_dict: dict[str, torch.Tensor]
    #: Règle de décision calibrée sur la validation (voir ``eval.classification``).
    decision: dict[str, float] | None = None
    #: Informations de traçabilité (époque, métrique, empreinte de config…), types simples.
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_model(cls, model: nn.Module, **fields: Any) -> ClassifierCheckpoint:
        state = {k: v.detach().to("cpu", copy=True) for k, v in model.state_dict().items()}
        return cls(state_dict=state, **fields)

    def build_model(self) -> nn.Module:
        model = build_classifier(self.arch, len(self.classes))
        model.load_state_dict(self.state_dict)
        model.eval()
        return model

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "format": CHECKPOINT_FORMAT,
            "arch": self.arch,
            "classes": list(self.classes),
            "input_size": self.input_size,
            "mean": list(self.mean),
            "std": list(self.std),
            "state_dict": self.state_dict,
            "decision": self.decision,
            "metadata": self.metadata,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save(payload, tmp)
        tmp.replace(path)  # jamais de checkpoint à moitié écrit
        return path

    @classmethod
    def load(cls, path: str | Path) -> ClassifierCheckpoint:
        payload = torch.load(Path(path), map_location="cpu", weights_only=True)
        found = payload.pop("format", None)
        if found != CHECKPOINT_FORMAT:
            raise ValueError(f"{path} : format {found!r}, attendu {CHECKPOINT_FORMAT!r}")
        return cls(**payload)
