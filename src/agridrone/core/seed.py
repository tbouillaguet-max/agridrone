"""Graines aléatoires et déterminisme.

``seed_everything`` fixe Python, NumPy et PyTorch (CPU, CUDA, MPS). Pour des
DataLoader reproductibles, passer ``worker_init_fn=seed_worker`` et
``generator=make_generator(seed)``.

Le mode ``deterministic=True`` force des algorithmes déterministes (cuDNN,
``torch.use_deterministic_algorithms``). Il est plus lent, et certaines
opérations n'ont pas d'implémentation déterministe : PyTorch émet alors un
avertissement (``warn_only=True``) plutôt que d'interrompre l'entraînement.
Sur GPU, ``CUBLAS_WORKSPACE_CONFIG`` doit être défini avant la première
opération CUDA : appeler ``seed_everything`` en tout début de programme.
"""

from __future__ import annotations

import os
import random

import numpy as np
import torch

_MAX_SEED = 2**32 - 1


def configure_determinism(enabled: bool) -> None:
    """Active ou désactive les algorithmes déterministes de PyTorch."""
    if enabled:
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.backends.cudnn.deterministic = enabled
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(enabled, warn_only=True)


def seed_everything(seed: int, *, deterministic: bool = False) -> int:
    """Fixe toutes les graines et renvoie la graine utilisée."""
    if not 0 <= seed <= _MAX_SEED:
        raise ValueError(f"La graine doit être dans [0, 2**32 - 1], reçu {seed}")
    # N'affecte que les sous-processus (le hash du processus courant est déjà fixé).
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    # RNG global legacy : encore utilisé par de nombreuses bibliothèques.
    np.random.seed(seed)  # noqa: NPY002
    torch.manual_seed(seed)  # couvre aussi CUDA et MPS
    configure_determinism(deterministic)
    return seed


def seed_worker(worker_id: int) -> None:
    """``worker_init_fn`` pour DataLoader : dérive les graines NumPy/Python du worker
    de la graine PyTorch (elle-même dérivée du ``generator`` du DataLoader).

    La graine du worker change à chaque époque et diffère d'un worker à l'autre. Un jeu
    de données qui a son propre générateur (``Compose`` d'albumentations, qui ignore les
    graines globales) expose une méthode ``reseed(seed)`` : elle est appelée ici. Sans
    cela, chaque worker rejouerait à chaque époque la même suite d'augmentations.
    """
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)  # noqa: NPY002
    random.seed(worker_seed)
    info = torch.utils.data.get_worker_info()
    reseed = getattr(info.dataset, "reseed", None) if info is not None else None
    if callable(reseed):
        reseed(worker_seed)


def make_generator(seed: int) -> torch.Generator:
    """Générateur dédié au DataLoader (ordre de mélange reproductible)."""
    generator = torch.Generator()
    generator.manual_seed(seed)
    return generator
