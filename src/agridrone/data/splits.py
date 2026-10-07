"""Découpage train/val/test par groupes : source, parcelle, date ou bloc spatial.

Jamais d'affectation image par image : tous les éléments d'un groupe vont dans le
même ensemble. Sinon un modèle est évalué sur des quasi-doublons d'images vues à
l'entraînement (même feuille, même session, tuiles voisines qui se chevauchent) et
les scores sont surestimés.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Hashable, Mapping, Sequence

from agridrone.data.tiling import Window


def _check_fractions(fractions: Mapping[str, float]) -> None:
    if not fractions or any(v <= 0 for v in fractions.values()):
        raise ValueError(f"fractions invalides : {dict(fractions)}")
    if abs(sum(fractions.values()) - 1.0) > 1e-6:
        raise ValueError(f"les fractions doivent sommer à 1 : {dict(fractions)}")


def group_split(
    groups: Sequence[Hashable], fractions: Mapping[str, float], *, seed: int = 0
) -> list[str]:
    """Renvoie l'ensemble de chaque élément ; un groupe entier va dans un seul ensemble.

    Les groupes sont pris du plus gros au plus petit (ordre aléatoire reproductible à
    taille égale) et chacun rejoint l'ensemble le plus en retard sur sa cible, compté
    en nombre d'éléments.
    """
    _check_fractions(fractions)
    sizes = Counter(groups)
    order = sorted(sizes, key=str)
    random.Random(seed).shuffle(order)
    order.sort(key=lambda g: -sizes[g])  # tri stable : l'ordre aléatoire départage
    n = len(groups)
    filled = dict.fromkeys(fractions, 0)
    assignment: dict[Hashable, str] = {}
    for group in order:
        split = max(fractions, key=lambda s: fractions[s] * n - filled[s])
        assignment[group] = split
        filled[split] += sizes[group]
    return [assignment[g] for g in groups]


def assert_no_group_leakage(groups: Sequence[Hashable], splits: Sequence[str | None]) -> None:
    """Lève ``AssertionError`` si un groupe apparaît dans plusieurs ensembles."""
    seen: dict[Hashable, set[str]] = defaultdict(set)
    for group, split in zip(groups, splits, strict=True):
        if split is not None:
            seen[group].add(split)
    leaking = {g: s for g, s in seen.items() if len(s) > 1}
    if leaking:
        raise AssertionError(f"groupes présents dans plusieurs ensembles : {leaking}")


def _blocks(window: Window, block: int) -> set[tuple[int, int]]:
    rows = range(window.row // block, (window.row + window.height - 1) // block + 1)
    cols = range(window.col // block, (window.col + window.width - 1) // block + 1)
    return {(r, c) for r in rows for c in cols}


def spatial_split(
    windows: Sequence[Window], block: int, fractions: Mapping[str, float], *, seed: int = 0
) -> list[str | None]:
    """Découpage spatial des tuiles d'une même orthophoto, par blocs carrés.

    L'image est quadrillée en blocs de ``block`` pixels (``block`` ≥ taille de
    tuile) ; chaque bloc reçoit un ensemble. Une tuile est rattachée au bloc de son
    centre et **écartée** (``None``) si elle déborde sur un bloc d'un autre ensemble :
    deux tuiles d'ensembles différents ne partagent donc jamais un pixel.
    """
    if any(max(w.height, w.width) > block for w in windows):
        raise ValueError("la taille de bloc doit être au moins égale à celle des tuiles")
    centers = [(int(w.center[0] // block), int(w.center[1] // block)) for w in windows]
    window_splits = group_split(centers, fractions, seed=seed)
    block_split = dict(zip(centers, window_splits, strict=True))
    result: list[str | None] = []
    for window, split in zip(windows, window_splits, strict=True):
        touched = {block_split.get(b, split) for b in _blocks(window, block)}
        result.append(split if touched == {split} else None)
    return result
