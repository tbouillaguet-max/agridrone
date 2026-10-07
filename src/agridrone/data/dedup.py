"""Détection de doublons et quasi-doublons d'images.

Indispensable ici : de nombreux jeux publics se recopient entre eux (par exemple les
images John Innes republiées dans d'autres jeux Kaggle). Une même image présente
dans l'entraînement et dans le test fausserait l'évaluation inter-sources.

* doublons exacts : sha1 du fichier ;
* quasi-doublons, en deux étapes : candidats par *difference hash* 64 bits (rapide,
  rappel élevé), puis confirmation par dHash 256 bits (précis). Sur les données du
  projet, les vrais doublons ont une distance 256 bits < 10, les images seulement
  semblables (feuilles de même texture) > 20 : la confirmation élimine ces faux
  positifs. Les hashes constants (images quasi uniformes) ne sont jamais appariés.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image


def file_sha1(path: str | Path) -> str:
    digest = hashlib.sha1(usedforsecurity=False)
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dhash_words(image: Image.Image, side: int) -> np.ndarray:
    small = image.convert("L").resize((side + 1, side), Image.Resampling.LANCZOS)
    pixels = np.asarray(small, dtype=np.int16)
    bits = (pixels[:, 1:] > pixels[:, :-1]).flatten()
    return np.packbits(bits).view(">u8").astype(np.uint64)


def dhash(image: Image.Image | str | Path) -> int:
    """dHash 64 bits : compare chaque pixel à son voisin de droite sur une vignette
    en niveaux de gris de 9 × 8 pixels."""
    if not isinstance(image, Image.Image):
        with Image.open(image) as img:
            return dhash(img)
    return int(_dhash_words(image, 8)[0])


def dhash256(image: Image.Image | str | Path) -> str:
    """dHash 256 bits (vignette 17 × 16), renvoyé en hexadécimal (64 caractères)."""
    if not isinstance(image, Image.Image):
        with Image.open(image) as img:
            return dhash256(img)
    return "".join(f"{int(w):016x}" for w in _dhash_words(image, 16))


def hex_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


_CONSTANT = (np.uint64(0), np.uint64(2**64 - 1))


def near_duplicate_pairs(
    hashes: np.ndarray, max_distance: int = 4, chunk: int = 2048
) -> list[tuple[int, int, int]]:
    """Couples (i, j, distance) avec i < j et distance de Hamming ≤ ``max_distance``.

    Les hashes constants (tout à 0 ou tout à 1 : images quasi uniformes) sont ignorés.
    """
    h = np.asarray(hashes, dtype=np.uint64)
    informative = ~np.isin(h, _CONSTANT)
    pairs: list[tuple[int, int, int]] = []
    for start in range(0, len(h), chunk):
        block = h[start : start + chunk]
        dist = np.bitwise_count(block[:, None] ^ h[None, :])
        dist[~informative[start : start + chunk], :] = 255
        dist[:, ~informative] = 255
        rows, cols = np.nonzero(dist <= max_distance)
        for r, c in zip(rows.tolist(), cols.tolist(), strict=True):
            i = start + r
            if i < c:
                pairs.append((i, c, int(dist[r, c])))
    return pairs


def confirm_pairs(
    pairs: list[tuple[int, int, int]], hashes256: list[str], max_distance: int = 12
) -> list[tuple[int, int, int]]:
    """Garde les couples candidats dont la distance dHash 256 bits est ≤ ``max_distance``."""
    confirmed = []
    for i, j, _ in pairs:
        d = hex_distance(hashes256[i], hashes256[j])
        if d <= max_distance:
            confirmed.append((i, j, d))
    return confirmed


def cluster_ids(n: int, pairs: list[tuple[int, int, int]]) -> list[int]:
    """Composantes connexes (union-find) : un identifiant de groupe par élément."""
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, _ in pairs:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)
    return [find(i) for i in range(n)]
