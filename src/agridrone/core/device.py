"""Sélection du device de calcul : CUDA, puis MPS (Apple Silicon), puis CPU.

Une demande explicite (``"cuda"``, ``"cuda:1"``, ``"mps"``) qui ne peut pas être
satisfaite lève une erreur au lieu de basculer en silence sur le CPU : un
entraînement lancé « sur GPU » qui tourne en réalité sur CPU fausse les temps
mesurés et les comparaisons.
"""

from __future__ import annotations

import contextlib
import os
import platform
from typing import Any, Literal

import torch

#: Précision de calcul : float32, ou bfloat16 par autocast (poids maîtres en float32).
Precision = Literal["fp32", "bf16"]


class DeviceUnavailableError(RuntimeError):
    """Le device demandé n'est pas disponible sur cette machine."""


def mps_available() -> bool:
    backend = getattr(torch.backends, "mps", None)
    return bool(backend is not None and backend.is_available())


def resolve_device(request: str = "auto") -> torch.device:
    """Convertit une demande (``auto|cpu|mps|cuda|cuda:N``) en ``torch.device``."""
    req = request.strip().lower()
    if req == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda", 0)
        if mps_available():
            return torch.device("mps")
        return torch.device("cpu")
    if req == "cpu":
        return torch.device("cpu")
    if req == "mps":
        if not mps_available():
            raise DeviceUnavailableError("MPS demandé mais indisponible (Apple Silicon requis).")
        return torch.device("mps")
    if req == "cuda" or req.startswith("cuda:"):
        if not torch.cuda.is_available():
            raise DeviceUnavailableError(
                f"{request!r} demandé mais CUDA est indisponible "
                "(pas de GPU NVIDIA visible, ou PyTorch installé sans CUDA)."
            )
        try:
            device = torch.device(req)
        except RuntimeError as exc:
            raise ValueError(f"Device invalide : {request!r}") from exc
        index = 0 if device.index is None else device.index
        if index >= torch.cuda.device_count():
            raise DeviceUnavailableError(
                f"{request!r} demandé mais seulement {torch.cuda.device_count()} GPU visible(s)."
            )
        return torch.device("cuda", index)
    raise ValueError(f"Device inconnu : {request!r} (attendu : auto, cpu, mps, cuda, cuda:N)")


def to_ultralytics_device(device: torch.device) -> str:
    """Traduit un ``torch.device`` dans la syntaxe d'Ultralytics (``"0"``, ``"mps"``, ``"cpu"``)."""
    if device.type == "cuda":
        return str(device.index or 0)
    return device.type


def describe_device(device: torch.device) -> dict[str, Any]:
    """Informations utiles à journaliser avec chaque run."""
    info: dict[str, Any] = {
        "device": str(device),
        "torch": torch.__version__,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "torch_threads": torch.get_num_threads(),
    }
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(device)
        info.update(
            gpu_name=props.name,
            gpu_memory_gb=round(props.total_memory / 1024**3, 2),
            compute_capability=f"{props.major}.{props.minor}",
            cuda_runtime=torch.version.cuda,
            cudnn=torch.backends.cudnn.version(),
        )
    elif device.type == "mps":
        info["mps_built"] = torch.backends.mps.is_built()
    return info


def autocast_context(
    device: torch.device, precision: Precision
) -> contextlib.AbstractContextManager[Any]:
    """Contexte de calcul : rien en ``fp32`` ; autocast bfloat16 en ``bf16``.

    Sur CPU, bf16 n'est rapide qu'avec les instructions AMX ou AVX512-BF16 (Xeon
    récents) ; sur GPU, il faut une architecture Ampere ou plus récente (Jetson Orin
    compris). Les pertes sont à calculer en float32, hors du contexte.
    """
    if precision == "fp32":
        return contextlib.nullcontext()
    if precision == "bf16":
        return torch.autocast(device_type=device.type, dtype=torch.bfloat16)
    raise ValueError(f"Précision inconnue : {precision!r} (attendu : fp32, bf16)")
