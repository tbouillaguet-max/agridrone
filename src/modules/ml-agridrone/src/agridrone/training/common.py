"""Outils communs aux lanceurs d'entraînement : DataLoader reproductible, planning du
taux d'apprentissage, courbes d'apprentissage."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import DataLoader, Dataset

from agridrone.core.seed import make_generator, seed_worker


def worker_init(worker_id: int) -> None:
    """Graines du worker (voir ``seed_worker``) et OpenCV sans threads : les workers
    sont déjà parallèles entre eux, des threads en plus se disputeraient les cœurs."""
    import cv2

    cv2.setNumThreads(0)
    seed_worker(worker_id)


def make_loader(
    dataset: Dataset[Any],
    *,
    batch_size: int,
    shuffle: bool,
    num_workers: int,
    seed: int,
    drop_last: bool = False,
    pin_memory: bool = False,
) -> DataLoader[Any]:
    """DataLoader reproductible : ordre de mélange et augmentations fixés par ``seed``."""
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        drop_last=drop_last,
        num_workers=num_workers,
        worker_init_fn=worker_init,
        generator=make_generator(seed),
        pin_memory=pin_memory,
    )


def warmup_cosine(
    warmup_steps: int, total_steps: int, min_ratio: float = 0.0
) -> Callable[[int], float]:
    """Facteur de taux d'apprentissage par pas : montée linéaire puis décroissance en
    cosinus jusqu'à ``min_ratio`` (à passer à ``torch.optim.lr_scheduler.LambdaLR``)."""
    if total_steps < 1 or not 0 <= warmup_steps <= total_steps:
        raise ValueError(f"pas invalides : warmup={warmup_steps}, total={total_steps}")

    def factor(step: int) -> float:
        if step < warmup_steps:
            return (step + 1) / warmup_steps
        progress = min(1.0, (step - warmup_steps) / max(1, total_steps - warmup_steps))
        return min_ratio + (1.0 - min_ratio) * 0.5 * (1.0 + math.cos(math.pi * progress))

    return factor


def balanced_class_weights(labels: Sequence[int], n_classes: int) -> torch.Tensor:
    """Poids N / (K · n_k) : chaque classe pèse autant dans la perte."""
    counts = torch.bincount(torch.as_tensor(list(labels), dtype=torch.long), minlength=n_classes)
    if (counts == 0).any():
        missing = [i for i, c in enumerate(counts.tolist()) if c == 0]
        raise ValueError(f"classes sans aucune image d'entraînement : {missing}")
    return (counts.sum() / (n_classes * counts)).float()


def plot_history(history: Sequence[dict[str, float]], path: Path, *, metric: str) -> Path:
    """Deux panneaux côte à côte (échelles différentes, jamais deux axes y) :
    perte d'entraînement (et de validation si ``val_loss`` est fourni), puis la
    métrique de validation."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    epochs = [h["epoch"] for h in history]
    blue, orange, ink, grid = "#2a78d6", "#eb6834", "#1f2328", "#d9dde3"
    fig, (ax_loss, ax_metric) = plt.subplots(1, 2, figsize=(9, 3.2), layout="constrained")
    ax_loss.plot(epochs, [h["train_loss"] for h in history], color=blue, lw=2, label="entraînement")
    if all("val_loss" in h for h in history):
        ax_loss.plot(
            epochs, [h["val_loss"] for h in history], color=orange, lw=2, label="validation"
        )
        ax_loss.legend(frameon=False, fontsize=9)
    ax_loss.set_title("perte", fontsize=10, color=ink)
    ax_metric.plot(epochs, [h[metric] for h in history], color=blue, lw=2, marker="o", ms=4)
    ax_metric.set_title(f"{metric} (validation)", fontsize=10, color=ink)
    best = max(range(len(history)), key=lambda i: history[i][metric])
    ax_metric.annotate(
        f"meilleure : {history[best][metric]:.3f}",
        (epochs[best], history[best][metric]),
        textcoords="offset points",
        xytext=(0, -16),
        ha="center",
        fontsize=8,
        color=ink,
    )
    for ax in (ax_loss, ax_metric):
        ax.set_xlabel("époque", fontsize=9)
        ax.grid(True, color=grid, lw=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
