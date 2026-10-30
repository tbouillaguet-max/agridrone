"""Instantané de l'environnement d'exécution, enregistré avec chaque run."""

from __future__ import annotations

import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

TRACKED_PACKAGES = (
    "agridrone",
    "torch",
    "torchvision",
    "timm",
    "segmentation-models-pytorch",
    "ultralytics",
    "albumentations",
    "opencv-python-headless",
    "rasterio",
    "numpy",
    "mlflow",
)


def package_versions(names: tuple[str, ...] = TRACKED_PACKAGES) -> dict[str, str | None]:
    """Versions installées (``None`` si le paquet est absent)."""
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip()


def git_info(root: Path) -> dict[str, Any]:
    """Commit, branche et état « modifié » du dépôt (valeurs ``None`` hors dépôt git).

    Un run lancé avec ``git_dirty=True`` n'est pas reproductible à partir du
    seul commit : le signaler dans les résultats.
    """
    status = _git(["status", "--porcelain", "--untracked-files=no"], root)
    return {
        "git_commit": _git(["rev-parse", "HEAD"], root),
        "git_branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], root),
        "git_dirty": None if status is None else bool(status),
    }


def environment_snapshot(root: Path) -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        **git_info(root),
        "packages": package_versions(),
    }
