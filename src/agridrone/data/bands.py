"""Capteurs et bandes spectrales nommées : base du code générique en N bandes.

Les bandes sont toujours désignées par leur **nom** (``blue``, ``green``, ``red``,
``red_edge``, ``nir``…), jamais par leur position : l'ordre change d'un capteur à
l'autre. MicaSense RedEdge range ses bandes B, V, R, **PIR, RE** (tableau 1 de
l'article Ir-UNet, 2021), la DJI P4 Multispectral B, V, R, **RE, PIR**. Un modèle
est entraîné sur une liste ordonnée de noms ; :func:`select_bands` réordonne
n'importe quelle image vers cette liste.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agridrone.core.config import ConfigError, load_yaml

#: Noms de bandes connus (le code les compare, l'orthographe compte).
KNOWN_BANDS = frozenset(
    {
        "blue",
        "green",
        "red",
        "red_edge",
        "nir",
        "coastal_blue",
        "green_531",
        "red_650",
        "red_edge_705",
        "red_edge_740",
        "thermal",
        "panchromatic",
        "alpha",
    }
)


class BandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    center_nm: float | None = None
    fwhm_nm: float | None = None

    @field_validator("name")
    @classmethod
    def _known(cls, value: str) -> str:
        if value not in KNOWN_BANDS:
            raise ValueError(
                f"bande inconnue {value!r} (connues : {', '.join(sorted(KNOWN_BANDS))})"
            )
        return value


class SensorSpec(BaseModel):
    """Description d'un capteur : bandes dans l'ordre où elles sont stockées."""

    model_config = ConfigDict(extra="forbid")

    name: str
    bands: list[BandSpec]
    #: Valeurs de réflectance calibrée (True) ou comptes / 8 bits normalisés (False).
    reflectance: bool = False
    #: Facteur ramenant les valeurs stockées en réflectance [0, 1] (1e-4 pour uint16 ×10000).
    scale: float = 1.0
    source: str = Field(default="", description="référence des longueurs d'onde")

    @field_validator("bands")
    @classmethod
    def _unique(cls, bands: list[BandSpec]) -> list[BandSpec]:
        names = [b.name for b in bands]
        if len(set(names)) != len(names):
            raise ValueError(f"bandes en double : {names}")
        return bands

    @property
    def band_names(self) -> list[str]:
        return [b.name for b in self.bands]

    def index(self, name: str) -> int:
        try:
            return self.band_names.index(name)
        except ValueError:
            raise KeyError(f"le capteur {self.name!r} n'a pas de bande {name!r}") from None


def load_sensor(path: str | Path) -> SensorSpec:
    try:
        return SensorSpec.model_validate(load_yaml(path))
    except ValueError as exc:
        raise ConfigError(f"{path} : capteur invalide\n{exc}") from exc


def select_bands(
    array: np.ndarray, sensor: SensorSpec, wanted: Sequence[str], *, channel_axis: int = 0
) -> np.ndarray:
    """Extrait et réordonne les bandes ``wanted`` (par nom) d'une image du capteur."""
    if array.shape[channel_axis] != len(sensor.bands):
        raise ValueError(
            f"{array.shape[channel_axis]} canaux sur l'axe {channel_axis}, "
            f"{len(sensor.bands)} attendus pour {sensor.name}"
        )
    indices = [sensor.index(name) for name in wanted]
    return np.take(array, indices, axis=channel_axis)
