from __future__ import annotations

import random

import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader, Dataset

from agridrone.core.seed import make_generator, seed_everything, seed_worker


def _draw() -> tuple[float, float, list[float]]:
    return random.random(), float(np.random.rand()), torch.rand(3).tolist()


def test_same_seed_same_draws() -> None:
    seed_everything(123)
    first = _draw()
    seed_everything(123)
    assert _draw() == first
    seed_everything(124)
    assert _draw() != first


@pytest.mark.parametrize("bad", [-1, 2**32])
def test_seed_range(bad: int) -> None:
    with pytest.raises(ValueError):
        seed_everything(bad)


def test_deterministic_mode_toggles_torch_flags() -> None:
    seed_everything(0, deterministic=True)
    assert torch.are_deterministic_algorithms_enabled()
    assert torch.backends.cudnn.deterministic
    seed_everything(0, deterministic=False)
    assert not torch.are_deterministic_algorithms_enabled()


class _NumpyNoise(Dataset[float]):
    """Imite une augmentation aléatoire faite avec NumPy dans un worker."""

    def __len__(self) -> int:
        return 8

    def __getitem__(self, index: int) -> float:
        return float(np.random.rand())


def _epoch(seed: int) -> list[float]:
    loader = DataLoader(
        _NumpyNoise(),
        batch_size=2,
        shuffle=True,
        num_workers=2,
        worker_init_fn=seed_worker,
        generator=make_generator(seed),
    )
    return [v for batch in loader for v in batch.tolist()]


# fork() dans un processus multi-threadé : bénin ici (workers sans threads).
@pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")
def test_dataloader_workers_are_reproducible() -> None:
    first = _epoch(7)
    assert _epoch(7) == first
    assert _epoch(8) != first
    assert len(set(first)) == len(first)  # pas de tirages dupliqués entre workers
