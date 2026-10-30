"""Métriques de segmentation sémantique : IoU et F1 (Dice) par classe, mIoU.

Les pixels ``ignore_index`` (255 : non annotés, hors image) ne comptent pas. Les
métriques sont calculées sur la matrice de confusion cumulée de tout un ensemble
(et non moyennées image par image) : une image presque vide ne pèse pas autant
qu'une image pleine de végétation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from agridrone.eval.classification import GRID, INK, SERIES_COLORS

IGNORE_INDEX = 255


def pixel_confusion(
    y_true: np.ndarray, y_pred: np.ndarray, n_classes: int, ignore_index: int = IGNORE_INDEX
) -> np.ndarray:
    """Matrice (K, K) : lignes = vérité, colonnes = prédiction ; pixels ignorés exclus."""
    if y_true.shape != y_pred.shape:
        raise ValueError(f"tailles différentes : {y_true.shape} et {y_pred.shape}")
    keep = y_true != ignore_index
    t = y_true[keep].astype(np.int64)
    p = y_pred[keep].astype(np.int64)
    if t.size and (t.max() >= n_classes or p.min() < 0 or p.max() >= n_classes):
        raise ValueError("classe hors de [0, K)")
    return np.bincount(t * n_classes + p, minlength=n_classes**2).reshape(n_classes, n_classes)


def merge_confusion(cm: np.ndarray, groups: Sequence[Sequence[int]]) -> np.ndarray:
    """Regroupe des classes : ``groups[g]`` liste les classes fusionnées dans la classe g."""
    flat = [c for group in groups for c in group]
    if sorted(flat) != list(range(cm.shape[0])):
        raise ValueError("chaque classe doit appartenir à exactement un groupe")
    out = np.zeros((len(groups), len(groups)), dtype=cm.dtype)
    for a, rows in enumerate(groups):
        for b, cols in enumerate(groups):
            out[a, b] = cm[np.ix_(list(rows), list(cols))].sum()
    return out


def segmentation_scores(cm: np.ndarray, classes: Sequence[str]) -> dict[str, Any]:
    """IoU, F1, précision, rappel par classe ; mIoU et F1 macro sur les classes présentes."""
    tp = np.diag(cm).astype(np.float64)
    truth = cm.sum(axis=1).astype(np.float64)
    predicted = cm.sum(axis=0).astype(np.float64)
    per_class: dict[str, dict[str, float | int | None]] = {}
    for i, name in enumerate(classes):
        union = truth[i] + predicted[i] - tp[i]
        present = truth[i] > 0
        per_class[name] = {
            "pixels": int(truth[i]),
            "iou": float(tp[i] / union) if present else None,
            "f1": float(2 * tp[i] / (truth[i] + predicted[i])) if present else None,
            "precision": float(tp[i] / predicted[i]) if predicted[i] else None,
            "recall": float(tp[i] / truth[i]) if present else None,
        }
    present = [m for m in per_class.values() if m["iou"] is not None]
    total = cm.sum()
    return {
        "miou": float(np.mean([m["iou"] for m in present])) if present else None,
        "macro_f1": float(np.mean([m["f1"] for m in present])) if present else None,
        "pixel_accuracy": float(tp.sum() / total) if total else None,
        "per_class": per_class,
        "confusion": cm.tolist(),
    }


def plot_iou_comparison(
    scores: Mapping[str, Mapping[str, float | None]],
    classes: Sequence[str],
    path: str | Path,
    *,
    title: str,
) -> Path:
    """Barres groupées : IoU par classe (groupes) pour chaque méthode (couleurs).

    ``scores[méthode][classe]`` ; une valeur ``None`` (méthode sans cette classe) est
    laissée vide et signalée par « — ».
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    methods = list(scores)
    if len(methods) > len(SERIES_COLORS):
        raise ValueError(f"{len(methods)} méthodes : au plus {len(SERIES_COLORS)}")
    width = 0.8 / len(methods)
    fig, ax = plt.subplots(figsize=(1.9 * len(classes) + 3.2, 3.9), layout="constrained")
    x = np.arange(len(classes))
    for m, (method, color) in enumerate(zip(methods, SERIES_COLORS, strict=False)):
        offsets = x - 0.4 + width * (m + 0.5)
        for xi, cls in zip(offsets, classes, strict=True):
            value = scores[method].get(cls)
            if value is None:
                ax.text(xi, 0.01, "—", ha="center", va="bottom", fontsize=8, color=INK)
                continue
            # 2 px d'écart entre barres voisines (bord blanc), extrémité de donnée nette.
            ax.bar(xi, value, width=width, color=color, edgecolor="white", linewidth=1.5)
            ax.text(xi, value + 0.01, f"{value:.2f}", ha="center", va="bottom", fontsize=7.5)
        ax.bar(0, 0, color=color, label=method)  # entrée de légende
    ax.set_xticks(x, list(classes))
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("IoU (test)", color=INK)
    ax.set_title(title, fontsize=11, color=INK)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncols=min(4, len(methods)),
        frameon=False,
        fontsize=9,
    )
    ax.grid(True, axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def false_color(image: np.ndarray, bands: Sequence[str]) -> np.ndarray:
    """Composition colorée (H, W, 3) dans [0, 1] pour l'affichage.

    PIR-R-V (végétation en rouge) si les bandes existent, sinon R-V-B ; étirement
    2–98 % par canal.
    """
    wanted = ("nir", "red", "green") if {"nir", "red", "green"} <= set(bands) else None
    if wanted is None:
        wanted = ("red", "green", "blue")
    rgb = np.stack([image[list(bands).index(b)] for b in wanted], axis=-1).astype(np.float32)
    low, high = np.nanpercentile(rgb, [2, 98], axis=(0, 1))
    stretched: np.ndarray = np.clip((rgb - low) / np.maximum(high - low, 1e-6), 0, 1)
    return stretched


def plot_examples(
    rows: Sequence[Mapping[str, np.ndarray]],
    columns: Sequence[str],
    class_colors: Sequence[str],
    class_names: Sequence[str],
    path: str | Path,
    *,
    title: str,
) -> Path:
    """Grille d'exemples : une ligne par image, une colonne par élément de ``columns``.

    ``rows[i][col]`` : image (H, W, 3) dans [0, 1] ou masque (H, W) d'entiers
    (255 = ignoré, affiché en blanc).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgb
    from matplotlib.patches import Patch

    palette = np.array([to_rgb(c) for c in class_colors] + [to_rgb("#ffffff")])
    fig, axes = plt.subplots(
        len(rows),
        len(columns),
        figsize=(2.6 * len(columns), 2.6 * len(rows) + 0.6),
        layout="constrained",
        squeeze=False,
    )
    for r, row in enumerate(rows):
        for c, name in enumerate(columns):
            ax = axes[r, c]
            data = row[name]
            if data.ndim == 2:
                idx = np.where(data == IGNORE_INDEX, len(class_colors), data)
                data = palette[idx]
            ax.imshow(data, interpolation="nearest")
            ax.set_xticks([])
            ax.set_yticks([])
            if r == 0:
                ax.set_title(name, fontsize=9, color=INK)
    handles = [Patch(color=col, label=n) for col, n in zip(class_colors, class_names, strict=True)]
    fig.legend(
        handles=handles,
        loc="lower center",
        ncols=len(handles),
        frameon=False,
        fontsize=9,
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.suptitle(title, fontsize=11, color=INK)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return path
