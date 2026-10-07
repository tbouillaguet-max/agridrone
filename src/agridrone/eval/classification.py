"""Métriques de classification, sortie « incertain » et règle de décision.

Le modèle produit des probabilités softmax (N, K). Une décision vaut l'indice d'une
classe, ou :data:`UNCERTAIN` (-1) quand la règle s'abstient : l'image est alors
signalée pour un second regard (nouvelle prise de vue, vérification humaine).

Règle de décision (:class:`DecisionRule`), avec **priorité au rappel des maladies** :

* « incertain » si la probabilité maximale est < ``tau``. ``tau`` est calibré sur la
  validation pour garder une part ``target_coverage`` des images ;
* « sain » exige en plus p(sain) >= ``tau_healthy``, faute de quoi l'image est
  « incertaine ». Une plante malade déclarée saine est l'erreur la plus coûteuse : la
  maladie ne sera pas traitée. ``tau_healthy`` est le plus petit seuil qui ramène, sur
  la validation, la part d'images malades déclarées saines sous ``max_missed_rate``.

Conventions des métriques :

* les classes absentes d'un jeu (tests inter-sources) n'entrent pas dans le macro-F1 ;
  une prédiction vers une classe absente reste une erreur ;
* avec abstention, une image « incertaine » compte comme non reconnue pour le rappel
  et l'exactitude ; l'exactitude sélective ne porte que sur les images décidées.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

UNCERTAIN = -1

#: Palette catégorielle validée (ordre fixe, une couleur par série, jamais recyclée).
SERIES_COLORS = (
    "#2a78d6",
    "#eb6834",
    "#1baf7a",
    "#eda100",
    "#e87ba4",
    "#008300",
    "#4a3aa7",
    "#e34948",
)
INK, INK_MUTED, GRID = "#1f2328", "#52514e", "#d9dde3"


@dataclass(frozen=True)
class DecisionRule:
    tau: float
    tau_healthy: float
    healthy_index: int

    def apply(self, probs: np.ndarray) -> np.ndarray:
        """Décisions (N,) : indice de classe ou ``UNCERTAIN``."""
        p = np.asarray(probs, dtype=np.float64)
        pred = p.argmax(axis=1)
        conf = p.max(axis=1)
        decided = np.where(conf >= self.tau, pred, UNCERTAIN)
        decided[(pred == self.healthy_index) & (conf < self.tau_healthy)] = UNCERTAIN
        return decided

    def to_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> DecisionRule:
        return cls(float(data["tau"]), float(data["tau_healthy"]), int(data["healthy_index"]))


def calibrate_decision_rule(
    probs: np.ndarray,
    y_true: np.ndarray,
    healthy_index: int,
    *,
    target_coverage: float,
    max_missed_rate: float,
) -> DecisionRule:
    """Calibre ``tau`` et ``tau_healthy`` sur un jeu de validation (voir le module)."""
    if not 0.0 < target_coverage <= 1.0:
        raise ValueError(f"target_coverage doit être dans ]0, 1], reçu {target_coverage}")
    if not 0.0 <= max_missed_rate <= 1.0:
        raise ValueError(f"max_missed_rate doit être dans [0, 1], reçu {max_missed_rate}")
    p = np.asarray(probs, dtype=np.float64)
    y = np.asarray(y_true)
    conf = p.max(axis=1)
    pred = p.argmax(axis=1)
    tau = 0.0
    if target_coverage < 1.0:
        tau = float(np.quantile(conf, 1.0 - target_coverage, method="lower"))

    diseased = y != healthy_index
    # Malades déclarées saines avec ``tau`` seul : leur p(sain) trié par ordre croissant.
    missed = np.sort(conf[diseased & (pred == healthy_index) & (conf >= tau)])
    allowed = int(np.floor(max_missed_rate * diseased.sum() + 1e-9))
    tau_healthy = tau
    excess = len(missed) - allowed
    if excess > 0:  # écarter les ``excess`` ratés les moins sûrs : seuil juste au-dessus
        tau_healthy = max(tau, float(np.nextafter(missed[excess - 1], np.inf)))
    return DecisionRule(tau=tau, tau_healthy=tau_healthy, healthy_index=healthy_index)


def confusion_matrix(y_true: np.ndarray, y_pred: np.ndarray, n_classes: int) -> np.ndarray:
    """Matrice (K, K + 1) : lignes = vraie classe, colonnes = décision ; la dernière
    colonne compte les « incertain »."""
    y = np.asarray(y_true, dtype=np.int64)
    pred = np.asarray(y_pred, dtype=np.int64)
    if y.shape != pred.shape:
        raise ValueError(f"tailles différentes : {y.shape} et {pred.shape}")
    if y.size and (y.min() < 0 or y.max() >= n_classes):
        raise ValueError("étiquette hors de [0, K)")
    if pred.size and (pred.min() < UNCERTAIN or pred.max() >= n_classes):
        raise ValueError("prédiction hors de [0, K) ∪ {UNCERTAIN}")
    cm = np.zeros((n_classes, n_classes + 1), dtype=np.int64)
    np.add.at(cm, (y, np.where(pred == UNCERTAIN, n_classes, pred)), 1)
    return cm


def per_class_metrics(cm: np.ndarray, classes: Sequence[str]) -> dict[str, dict[str, Any]]:
    """Précision, rappel, F1 par classe. ``None`` quand la valeur n'est pas définie
    (classe absente du jeu, ou jamais prédite pour la précision)."""
    k = len(classes)
    tp = np.diag(cm[:, :k])
    support = cm.sum(axis=1)
    predicted = cm[:, :k].sum(axis=0)
    report: dict[str, dict[str, Any]] = {}
    for i, name in enumerate(classes):
        precision = tp[i] / predicted[i] if predicted[i] else None
        recall = tp[i] / support[i] if support[i] else None
        f1: float | None = None
        if recall is not None:
            p = precision or 0.0
            f1 = 2 * p * recall / (p + recall) if p + recall > 0 else 0.0
        report[name] = {
            "support": int(support[i]),
            "predicted": int(predicted[i]),
            "uncertain": int(cm[i, k]),
            "precision": None if precision is None else float(precision),
            "recall": None if recall is None else float(recall),
            "f1": None if f1 is None else float(f1),
        }
    return report


def summarize_predictions(
    y_true: np.ndarray, y_pred: np.ndarray, classes: Sequence[str], healthy_index: int
) -> dict[str, Any]:
    """Métriques globales, par classe et binaires (sain / malade) d'un jeu de décisions."""
    y = np.asarray(y_true, dtype=np.int64)
    pred = np.asarray(y_pred, dtype=np.int64)
    cm = confusion_matrix(y, pred, len(classes))
    per_class = per_class_metrics(cm, classes)
    present = [m for m in per_class.values() if m["support"] > 0]
    accepted = pred != UNCERTAIN
    diseased = y != healthy_index
    said_healthy = pred == healthy_index
    said_disease = accepted & ~said_healthy

    def rate(mask: np.ndarray, among: np.ndarray) -> float | None:
        return float(mask[among].mean()) if among.any() else None

    return {
        "n": len(y),
        "coverage": float(accepted.mean()) if len(y) else None,
        "accuracy": float((pred == y).mean()) if len(y) else None,
        "selective_accuracy": float((pred == y)[accepted].mean()) if accepted.any() else None,
        "macro_f1": float(np.mean([m["f1"] for m in present])) if present else None,
        "balanced_accuracy": float(np.mean([m["recall"] for m in present])) if present else None,
        "binary": {
            "n_diseased": int(diseased.sum()),
            "n_healthy": int((~diseased).sum()),
            # malade -> une maladie (la bonne ou une autre) : la plante sera inspectée
            "disease_detected": rate(said_disease, diseased),
            "disease_uncertain": rate(~accepted, diseased),
            # malade -> sain : l'erreur coûteuse
            "disease_missed": rate(said_healthy, diseased),
            "healthy_correct": rate(said_healthy, ~diseased),
            "healthy_uncertain": rate(~accepted, ~diseased),
            "healthy_false_alarm": rate(said_disease, ~diseased),
        },
        "per_class": per_class,
        "confusion": cm.tolist(),
    }


def expected_calibration_error(probs: np.ndarray, y_true: np.ndarray, n_bins: int = 15) -> float:
    """ECE : écart moyen (pondéré) entre confiance et exactitude, par tranche de confiance."""
    p = np.asarray(probs, dtype=np.float64)
    y = np.asarray(y_true)
    conf = p.max(axis=1)
    correct = p.argmax(axis=1) == y
    bins = np.minimum((conf * n_bins).astype(np.int64), n_bins - 1)
    ece = 0.0
    for b in np.unique(bins):
        in_bin = bins == b
        ece += in_bin.mean() * abs(correct[in_bin].mean() - conf[in_bin].mean())
    return float(ece)


def risk_coverage(probs: np.ndarray, y_true: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Courbe couverture → exactitude sélective, en gardant les images les plus sûres."""
    p = np.asarray(probs, dtype=np.float64)
    order = np.argsort(-p.max(axis=1), kind="stable")
    correct = (p.argmax(axis=1) == np.asarray(y_true))[order]
    kept = np.arange(1, len(correct) + 1)
    return kept / len(correct), np.cumsum(correct) / kept


def plot_risk_coverage(
    curves: Mapping[str, tuple[np.ndarray, np.ndarray]],
    path: str | Path,
    *,
    title: str,
    operating_points: Mapping[str, tuple[float, float]] | None = None,
) -> Path:
    """Exactitude sur les images décidées selon la couverture, une courbe par jeu.

    Les images sont gardées par confiance décroissante (voir :func:`risk_coverage`) ;
    à 100 % de couverture on lit l'exactitude sans abstention. ``operating_points``
    place la règle de décision calibrée (couverture, exactitude sélective) sur chaque
    courbe : un même seuil donne des couvertures très différentes d'un jeu à l'autre.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    if len(curves) > len(SERIES_COLORS):
        raise ValueError(f"{len(curves)} courbes : au plus {len(SERIES_COLORS)} par figure")
    fig, ax = plt.subplots(figsize=(7.2, 4.2), layout="constrained")
    ends: list[tuple[float, str]] = []
    for (name, (coverage, accuracy)), color in zip(curves.items(), SERIES_COLORS, strict=False):
        ax.plot(100 * coverage, 100 * accuracy, color=color, lw=2, label=name)
        ends.append((100 * float(accuracy[-1]), name))
        if operating_points and name in operating_points:
            cov, acc = operating_points[name]
            ax.plot(100 * cov, 100 * acc, "o", ms=8, color=color, mec="white", mew=2, zorder=3)
    # Étiquettes directes en bout de courbe, écartées si elles se chevauchent.
    placed: list[float] = []
    for y, name in sorted(ends):
        y = max(y, placed[-1] + 5.0) if placed else y
        placed.append(y)
        ax.annotate(
            name,
            xy=(100, y),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK,
            annotation_clip=False,
        )
    handles, _ = ax.get_legend_handles_labels()
    if operating_points:
        handles.append(
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                ms=7,
                color=INK_MUTED,
                mec="white",
                mew=2,
                label="règle de décision",
            )
        )
    ax.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncols=len(handles),
        frameon=False,
        fontsize=9,
    )
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 102)
    ax.set_xlabel("couverture : part des images décidées (%)", color=INK)
    ax.set_ylabel("exactitude sur les images décidées (%)", color=INK)
    ax.set_title(title, fontsize=11, color=INK)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_confusion(
    cm: np.ndarray,
    classes: Sequence[str],
    path: str | Path,
    *,
    title: str,
    with_uncertain: bool = True,
    uncertain_label: str = "incertain",
) -> Path:
    """Matrice de confusion normalisée par ligne (rappel), effectifs annotés.

    Seules les classes présentes dans le jeu apparaissent en lignes.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    k = len(classes)
    rows = [i for i in range(k) if cm[i].sum() > 0]
    data = cm[rows] if with_uncertain else cm[rows, :k]
    columns = [*classes, uncertain_label] if with_uncertain else list(classes)
    share = data / np.maximum(data.sum(axis=1, keepdims=True), 1)

    # Rampe séquentielle à une seule teinte (bleu), du presque blanc au bleu profond.
    cmap = LinearSegmentedColormap.from_list("agridrone_blue", ["#f4f7fb", "#2a78d6", "#0f3566"])
    fig, ax = plt.subplots(
        figsize=(1.2 * len(columns) + 2.2, 0.75 * len(rows) + 1.9), layout="constrained"
    )
    ax.imshow(share, cmap=cmap, vmin=0.0, vmax=1.0, aspect="auto")
    for r in range(len(rows)):
        for c in range(len(columns)):
            count = int(data[r, c])
            if count == 0:
                continue
            ink = "#ffffff" if share[r, c] > 0.55 else INK
            ax.text(
                c, r, f"{share[r, c]:.0%}\n{count}", ha="center", va="center", fontsize=9, color=ink
            )
    ax.set_xticks(range(len(columns)), columns, rotation=30, ha="right")
    ax.set_yticks(range(len(rows)), [classes[i] for i in rows])
    if with_uncertain:
        ax.axvline(k - 0.5, color="#ffffff", linewidth=3)
        ax.get_xticklabels()[-1].set_fontstyle("italic")
    ax.set_xlabel("décision du modèle")
    ax.set_ylabel("classe réelle")
    ax.set_title(title, fontsize=11)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
