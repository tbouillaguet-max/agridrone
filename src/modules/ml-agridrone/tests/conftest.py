from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(autouse=True)
def _restore_torch_determinism() -> Iterator[None]:
    """Les tests qui activent le mode déterministe ne doivent pas fuir sur les autres."""
    det = torch.are_deterministic_algorithms_enabled()
    warn_only = torch.is_deterministic_algorithms_warn_only_enabled()
    cudnn_det, cudnn_bench = torch.backends.cudnn.deterministic, torch.backends.cudnn.benchmark
    yield
    torch.use_deterministic_algorithms(det, warn_only=warn_only)
    torch.backends.cudnn.deterministic, torch.backends.cudnn.benchmark = cudnn_det, cudnn_bench


@pytest.fixture
def write_yaml(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Écrit un fichier YAML dans tmp_path et renvoie son chemin."""

    def _write(relative: str, content: str) -> Path:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    return _write
