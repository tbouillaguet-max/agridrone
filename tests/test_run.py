from __future__ import annotations

import json
from pathlib import Path

import pytest

from agridrone.cli import main
from agridrone.core.config import config_hash, load_experiment, validate_config
from agridrone.core.run import flatten, init_run, resolve_tracking_uri, tracking_run


def _cfg(tmp_path: Path, **extra: object):  # type: ignore[no-untyped-def]
    return validate_config(
        {
            "name": "unit",
            "device": "cpu",
            "paths": {"runs": str(tmp_path / "runs")},
            "tracking": {
                "enabled": False,
                "uri": f"sqlite:///{tmp_path / 'mlflow.db'}",
                "artifact_root": str(tmp_path / "artifacts"),
            },
            **extra,
        }
    )


def test_init_run_writes_reloadable_metadata(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path, seed=5)
    ctx = init_run(cfg, root=tmp_path)

    assert ctx.run_dir.parent == tmp_path / "runs" / "base"
    reloaded = load_experiment(ctx.run_dir / "config.yaml")
    assert reloaded == cfg
    assert config_hash(reloaded.model_dump(mode="json")) == ctx.config_hash

    env = json.loads((ctx.run_dir / "environment.json").read_text())
    assert env["config_hash"] == ctx.config_hash
    assert env["device"]["device"] == "cpu"
    assert env["packages"]["torch"]

    # Deux runs identiques dans la même seconde ne s'écrasent pas.
    assert init_run(cfg, root=tmp_path).run_dir != ctx.run_dir


def test_flatten_and_tracking_uri(tmp_path: Path) -> None:
    assert flatten({"a": {"b": 1, "c": {"d": [1]}}, "e": 2}) == {"a.b": 1, "a.c.d": [1], "e": 2}
    assert resolve_tracking_uri("sqlite:///mlflow.db", tmp_path) == (
        f"sqlite:///{(tmp_path / 'mlflow.db').resolve().as_posix()}"
    )
    assert resolve_tracking_uri("http://mlflow:5000", tmp_path) == "http://mlflow:5000"


def test_tracking_disabled_yields_none(tmp_path: Path) -> None:
    ctx = init_run(_cfg(tmp_path), root=tmp_path)
    with tracking_run(ctx) as run:
        assert run is None


@pytest.mark.slow
def test_tracking_logs_params_tags_and_artifacts(tmp_path: Path) -> None:
    import mlflow

    cfg = _cfg(tmp_path, seed=11)
    cfg = cfg.model_copy(update={"tracking": cfg.tracking.model_copy(update={"enabled": True})})
    ctx = init_run(cfg, root=tmp_path)
    with tracking_run(ctx) as run:
        mlflow.log_metric("loss", 0.5)
        run_id = run.info.run_id

    client = mlflow.MlflowClient(tracking_uri=f"sqlite:///{tmp_path / 'mlflow.db'}")
    logged = client.get_run(run_id)
    assert logged.data.params["seed"] == "11"
    assert logged.data.tags["config_hash"] == ctx.config_hash
    assert logged.data.metrics["loss"] == 0.5
    artifacts = {a.path for a in client.list_artifacts(run_id)}
    assert {"config.yaml", "environment.json"} <= artifacts
    assert (tmp_path / "artifacts" / "agridrone").is_dir()


BASE = str(Path(__file__).resolve().parents[1] / "configs" / "base.yaml")


def _smoke(tmp_path: Path, capsys: pytest.CaptureFixture[str], seed: int) -> str:
    code = main(
        [
            "smoke",
            "-c",
            BASE,
            "--steps",
            "5",
            f"seed={seed}",
            "device=cpu",
            "tracking.enabled=false",
            f"paths.runs={tmp_path / 'runs'}",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    return next(line for line in out.splitlines() if line.startswith("Perte finale"))


def test_cli_smoke_is_reproducible(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = _smoke(tmp_path, capsys, seed=3)
    assert _smoke(tmp_path, capsys, seed=3) == first
    assert _smoke(tmp_path, capsys, seed=4) != first


def test_cli_config_and_errors(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config", "-c", BASE, "seed=9", "name=essai"]) == 0
    out = capsys.readouterr().out
    assert "seed: 9" in out and "name: essai" in out and "config_hash:" in out

    assert main(["config", "-c", BASE, "seeed=9"]) == 2
    assert "seeed" in capsys.readouterr().err
