"""Baselines par indice de végétation (NDVI, NDRE) et seuillage d'Otsu.

Ces méthodes ne s'entraînent pas : un indice est calculé pixel par pixel à partir
des bandes **nommées**, puis découpé par un ou deux seuils. Les seuils sont estimés
sur l'ensemble d'entraînement seulement :

* **Otsu** (non supervisé) : seuil qui sépare au mieux l'histogramme de l'indice en
  deux modes ; « multi-Otsu » à deux seuils pour trois intervalles ;
* **seuil supervisé** : seuil qui maximise l'IoU de la végétation sur les masques
  d'entraînement, la meilleure performance possible d'un seuil unique sur cet indice.

L'indice est calculé sur les valeurs fournies (ici des comptes bruts non calibrés) :
ses seuils ne se transfèrent d'un vol à l'autre qu'avec une calibration radiométrique.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

#: Indice → (bande a, bande b) pour l'indice normalisé (a - b) / (a + b).
INDEX_BANDS: dict[str, tuple[str, str]] = {
    "ndvi": ("nir", "red"),
    "ndre": ("nir", "red_edge"),
}
#: Histogrammes sur [-1, 1] (domaine des indices normalisés).
HIST_BINS = 512
HIST_RANGE = (-1.0, 1.0)


def normalized_difference(a: np.ndarray, b: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """(a - b) / (a + b), en float32 ; NaN où a + b est nul ou non fini."""
    a = a.astype(np.float32, copy=False)
    b = b.astype(np.float32, copy=False)
    total = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        result: np.ndarray = (a - b) / total
    result[~np.isfinite(result) | (np.abs(total) < eps)] = np.nan
    return result


def compute_index(image: np.ndarray, bands: Sequence[str], name: str) -> np.ndarray:
    """Indice ``name`` d'une image (C, H, W) dont les bandes sont nommées ``bands``."""
    if name not in INDEX_BANDS:
        raise ValueError(f"indice inconnu {name!r} (connus : {sorted(INDEX_BANDS)})")
    if image.shape[0] != len(bands):
        raise ValueError(f"{image.shape[0]} canaux pour {len(bands)} noms de bandes")
    a, b = INDEX_BANDS[name]
    missing = [band for band in (a, b) if band not in bands]
    if missing:
        raise ValueError(f"{name} demande les bandes {missing}, absentes de {list(bands)}")
    return normalized_difference(image[list(bands).index(a)], image[list(bands).index(b)])


def index_histogram(values: np.ndarray) -> np.ndarray:
    """Histogramme (HIST_BINS,) des valeurs finies, sur HIST_RANGE."""
    finite = values[np.isfinite(values)]
    counts, _ = np.histogram(finite, bins=HIST_BINS, range=HIST_RANGE)
    hist: np.ndarray = counts.astype(np.float64)
    return hist


def _bin_edges() -> np.ndarray:
    return np.linspace(*HIST_RANGE, HIST_BINS + 1)


def _bin_centers() -> np.ndarray:
    edges = _bin_edges()
    centers: np.ndarray = (edges[:-1] + edges[1:]) / 2
    return centers


def otsu_threshold(hist: np.ndarray) -> float:
    """Seuil d'Otsu (maximise la variance inter-classes) d'un histogramme HIST_RANGE."""
    p = hist / hist.sum()
    centers = _bin_centers()
    w0 = np.cumsum(p)
    mu = np.cumsum(p * centers)
    w1 = 1.0 - w0
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu[-1] * w0 - mu) ** 2 / (w0 * w1)
    between[~np.isfinite(between)] = -1.0
    k = int(np.argmax(between))  # coupure entre la classe [0, k] et [k + 1, …]
    return float(_bin_edges()[k + 1])


def multi_otsu_thresholds(hist: np.ndarray) -> tuple[float, float]:
    """Deux seuils (trois classes) maximisant la variance inter-classes."""
    p = hist / hist.sum()
    centers = _bin_centers()
    cw = np.concatenate([[0.0], np.cumsum(p)])  # cw[i] = masse des cases [0, i)
    cm = np.concatenate([[0.0], np.cumsum(p * centers)])
    n = len(p)
    i = np.arange(1, n - 1)[:, None]  # première coupure : classes [0, i) | [i, j) | [j, n)
    j = np.arange(2, n)[None, :]
    valid = j > i

    def term(start: np.ndarray, stop: np.ndarray) -> np.ndarray:
        w = cw[stop] - cw[start]
        m = cm[stop] - cm[start]
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(w > 0, m**2 / w, 0.0)

    zero, end = np.zeros_like(i), np.full_like(j, n)
    score = term(zero, i) + term(i, j) + term(j, end)
    score = np.where(valid, score, -np.inf)
    a, b = np.unravel_index(int(np.argmax(score)), score.shape)
    edges = _bin_edges()
    return float(edges[int(i[a, 0])]), float(edges[int(j[0, b])])


@dataclass(frozen=True)
class IndexBaseline:
    """Découpe un indice par des seuils croissants ; ``labels[k]`` est la classe
    attribuée à l'intervalle k (``len(labels) == len(thresholds) + 1``)."""

    index: str
    thresholds: tuple[float, ...]
    labels: tuple[int, ...]
    method: str

    def __post_init__(self) -> None:
        if len(self.labels) != len(self.thresholds) + 1:
            raise ValueError("un label par intervalle attendu")
        if list(self.thresholds) != sorted(self.thresholds):
            raise ValueError("seuils non croissants")

    def predict(self, image: np.ndarray, bands: Sequence[str], nodata: int = 0) -> np.ndarray:
        """Masque (H, W) uint8 ; pixels où l'indice n'est pas défini : ``nodata``."""
        values = compute_index(image, bands, self.index)
        interval = np.digitize(values, self.thresholds)
        out: np.ndarray = np.asarray(self.labels, dtype=np.uint8)[interval]
        out[~np.isfinite(values)] = nodata
        return out


def best_supervised_threshold(
    hist_positive: np.ndarray, hist_negative: np.ndarray
) -> tuple[float, float]:
    """Seuil t maximisant l'IoU de la classe « positive » prédite par indice > t.

    ``hist_positive`` / ``hist_negative`` : histogrammes de l'indice sur les pixels
    positifs (végétation) et négatifs (fond). Renvoie (seuil, IoU d'entraînement).
    """
    # Prédire positif au-dessus de la coupure k : TP = positifs des cases >= k, etc.
    tp = np.cumsum(hist_positive[::-1])[::-1]
    fp = np.cumsum(hist_negative[::-1])[::-1]
    fn = hist_positive.sum() - tp
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = np.where(tp + fp + fn > 0, tp / (tp + fp + fn), 0.0)
    k = int(np.argmax(iou))
    return float(_bin_edges()[k]), float(iou[k])


def best_supervised_thresholds(
    hists: np.ndarray, labels: tuple[int, int, int]
) -> tuple[tuple[float, float], float]:
    """Deux seuils maximisant le mIoU des trois classes ``labels`` (une par intervalle,
    dans l'ordre croissant de l'indice) sur des histogrammes par classe (K, HIST_BINS).

    C'est la meilleure performance possible d'un découpage de l'indice en trois
    intervalles. Renvoie ((t1, t2), mIoU d'entraînement).
    """
    n = hists.shape[1]
    cum = np.concatenate([np.zeros((hists.shape[0], 1)), np.cumsum(hists, axis=1)], axis=1)
    total = cum[:, -1]
    everything = cum.sum(axis=0)  # pixels de toutes classes sous chaque bord
    i = np.arange(1, n - 1)[:, None]  # intervalles [0, i) | [i, j) | [j, n)
    j = np.arange(2, n)[None, :]
    l0, l1, l2 = labels
    tp = [cum[l0, i], cum[l1, j] - cum[l1, i], total[l2] - cum[l2, j]]
    predicted = [everything[i], everything[j] - everything[i], everything[-1] - everything[j]]
    ious = []
    for k, label in enumerate(labels):
        union = total[label] + predicted[k] - tp[k]
        with np.errstate(divide="ignore", invalid="ignore"):
            ious.append(np.where(union > 0, tp[k] / union, 0.0))
    miou = np.where(j > i, sum(ious) / 3, -np.inf)
    a, b = np.unravel_index(int(np.argmax(miou)), miou.shape)
    edges = _bin_edges()
    return (float(edges[int(i[a, 0])]), float(edges[int(j[0, b])])), float(miou[a, b])


def accumulate_histograms(
    samples: Iterable[tuple[np.ndarray, np.ndarray]],
    bands: Sequence[str],
    index: str,
    n_classes: int,
    ignore_index: int = 255,
) -> np.ndarray:
    """Histogrammes de l'indice par classe vraie : tableau (n_classes, HIST_BINS)."""
    hists = np.zeros((n_classes, HIST_BINS), np.float64)
    for image, mask in samples:
        values = compute_index(image, bands, index)
        for c in range(n_classes):
            hists[c] += index_histogram(values[(mask == c) & (mask != ignore_index)])
    return hists


def fit_index_baselines(
    hists: np.ndarray, index: str, *, background: int, vegetation: Sequence[int]
) -> dict[str, IndexBaseline]:
    """Baselines d'un indice à partir des histogrammes par classe de l'entraînement.

    * ``<indice>_otsu`` : fond / végétation (classes ``vegetation`` fusionnées) ;
    * ``<indice>_seuil_supervise`` : idem avec le seuil qui maximise l'IoU ;
    * ``<indice>_multi_otsu`` (si deux classes de végétation) : fond et deux classes,
      l'ordre des deux classes de végétation étant choisi sur l'entraînement ;
    * ``<indice>_2_seuils_supervises`` (idem) : les deux seuils et l'ordre qui
      maximisent le mIoU des trois classes, la meilleure performance possible d'un
      indice seul sur cette tâche.

    Les baselines binaires renvoient la première classe de ``vegetation`` pour tout
    pixel de végétation : elles s'évaluent sur la tâche fusionnée fond / végétation.
    """
    total = hists.sum(axis=0)
    veg = hists[list(vegetation)].sum(axis=0)
    first = vegetation[0]
    baselines = {
        f"{index}_otsu": IndexBaseline(
            index, (otsu_threshold(total),), (background, first), "otsu"
        ),
        f"{index}_seuil_supervise": IndexBaseline(
            index,
            (best_supervised_threshold(veg, hists[background])[0],),
            (background, first),
            "supervised",
        ),
    }
    if len(vegetation) == 2:
        t1, t2 = multi_otsu_thresholds(total)
        a, b = vegetation
        # Les seuils sont des bords de cases : les cases [0, lo) sont sous t1, etc.
        lo, hi = (int(np.searchsorted(_bin_edges(), t)) for t in (t1, t2))

        def hits(labels: tuple[int, int, int]) -> float:
            """Pixels d'entraînement bien classés avec cet ordre des intervalles."""
            return float(
                hists[labels[0], :lo].sum()
                + hists[labels[1], lo:hi].sum()
                + hists[labels[2], hi:].sum()
            )

        options = [(background, a, b), (background, b, a)]
        labels = max(options, key=hits)
        baselines[f"{index}_multi_otsu"] = IndexBaseline(index, (t1, t2), labels, "multi_otsu")
        fitted = {order: best_supervised_thresholds(hists, order) for order in options}
        order = max(fitted, key=lambda o: fitted[o][1])
        baselines[f"{index}_2_seuils_supervises"] = IndexBaseline(
            index, fitted[order][0], order, "supervised_3_classes"
        )
    return baselines
