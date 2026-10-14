"""Initialisation d'un run reproductible et suivi MLflow.

Chaque run produit un dossier ``<paths.runs>/<task>/<date>_<name>_<hash>/`` (par
exemple ``runs/ble/classification/...``) contenant :

* ``config.yaml`` — la config résolue et validée (héritage + surcharges) ;
* ``environment.json`` — commit git, état « modifié », versions des paquets,
  device, empreinte de la config.

Ces deux fichiers sont aussi attachés au run MLflow, avec la config aplatie en
paramètres. Relancer ``config.yaml`` sur le même commit reproduit le run.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import torch

from agridrone.core.config import ExperimentConfig, config_hash, dump_yaml
from agridrone.core.device import describe_device, resolve_device
from agridrone.core.env import environment_snapshot
from agridrone.core.paths import project_root, resolve_path
from agridrone.core.seed import seed_everything


@dataclass(frozen=True)
class RunContext:
    config: ExperimentConfig
    device: torch.device
    run_dir: Path
    root: Path
    config_hash: str
    environment: dict[str, Any]


def init_run(
    config: ExperimentConfig, *, root: Path | None = None, run_dir: Path | None = None
) -> RunContext:
    """Fixe les graines, choisit le device et écrit les métadonnées du run."""
    root = root or project_root()
    seed_everything(config.seed, deterministic=config.deterministic)
    device = resolve_device(config.device)

    resolved = config.model_dump(mode="json")
    digest = config_hash(resolved)
    if run_dir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = resolve_path(config.paths.runs, root) / config.task
        run_dir = base / f"{stamp}_{config.name}_{digest[:8]}"
        suffix = 1
        while run_dir.exists():
            suffix += 1
            run_dir = base / f"{stamp}_{config.name}_{digest[:8]}_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)

    environment = {
        **environment_snapshot(root),
        "config_hash": digest,
        "device": describe_device(device),
    }
    dump_yaml(resolved, run_dir / "config.yaml")
    (run_dir / "environment.json").write_text(
        json.dumps(environment, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return RunContext(config, device, run_dir, root, digest, environment)


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Aplatit un dictionnaire imbriqué : ``{"a": {"b": 1}}`` -> ``{"a.b": 1}``."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, Mapping):
            flat.update(flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def resolve_tracking_uri(uri: str, root: Path) -> str:
    """Rend absolu un chemin sqlite relatif (sinon MLflow le résout depuis le cwd)."""
    prefix = "sqlite:///"
    if uri.startswith(prefix):
        db = Path(uri.removeprefix(prefix))
        if not db.is_absolute():
            return prefix + (root / db).resolve().as_posix()
    return uri


@contextmanager
def tracking_run(ctx: RunContext, run_name: str | None = None) -> Iterator[Any]:
    """Ouvre un run MLflow (ou ne fait rien si ``tracking.enabled`` est faux).

    Renvoie l'objet ``mlflow.ActiveRun`` (ou ``None``) ; journaliser ensuite
    avec ``mlflow.log_metric`` etc.
    """
    tracking = ctx.config.tracking
    if not tracking.enabled:
        yield None
        return

    # Message d'aide de MLflow destiné aux assistants de code : bruit dans nos logs.
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    import mlflow  # import tardif : mlflow est long à importer

    mlflow.set_tracking_uri(resolve_tracking_uri(tracking.uri, ctx.root))
    if mlflow.get_experiment_by_name(tracking.experiment) is None:
        artifacts = resolve_path(tracking.artifact_root, ctx.root) / tracking.experiment
        mlflow.create_experiment(tracking.experiment, artifact_location=artifacts.as_uri())
    mlflow.set_experiment(tracking.experiment)

    env = ctx.environment
    with mlflow.start_run(run_name=run_name or ctx.run_dir.name) as run:
        mlflow.log_params(flatten(ctx.config.model_dump(mode="json")))
        mlflow.set_tags(
            {
                "task": ctx.config.task,
                "config_hash": ctx.config_hash,
                "device": str(ctx.device),
                "git_commit": str(env.get("git_commit")),
                "git_dirty": str(env.get("git_dirty")),
                "run_dir": str(ctx.run_dir),
            }
        )
        mlflow.log_artifact(str(ctx.run_dir / "config.yaml"))
        mlflow.log_artifact(str(ctx.run_dir / "environment.json"))
        yield run
