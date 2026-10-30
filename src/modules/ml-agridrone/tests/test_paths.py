from __future__ import annotations

from pathlib import Path

import pytest

from agridrone.core.paths import ROOT_ENV_VAR, project_root, resolve_path


def test_env_var_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(ROOT_ENV_VAR, str(tmp_path))
    assert project_root() == tmp_path.resolve()
    assert resolve_path("data/raw") == tmp_path.resolve() / "data/raw"


def test_root_found_from_subdirectory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(ROOT_ENV_VAR, raising=False)
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "configs").mkdir()
    sub = tmp_path / "notebooks" / "deep"
    sub.mkdir(parents=True)
    assert project_root(sub) == tmp_path.resolve()
    monkeypatch.chdir(sub)
    assert resolve_path("runs") == tmp_path.resolve() / "runs"


def test_absolute_path_unchanged(tmp_path: Path) -> None:
    assert resolve_path(tmp_path / "x", root=Path("/elsewhere")) == tmp_path / "x"
