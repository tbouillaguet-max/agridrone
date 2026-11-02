"""Fabrique de runs conformes, écrits à la main (indépendants du RunLogger).

Chaque test part d'un run valide puis le casse d'une seule façon : on vérifie
ainsi que le validateur détecte précisément chaque règle.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from ml_dashboard import standard as S

RUN_ID = "20261029_180500_test-run"


def _meta(task: str, status: str = "completed") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run_id": RUN_ID,
        "project": "demo",
        "task": task,
        "model": "efficientnet_b0" if task == "classification" else "yolov8n",
        "framework": "pytorch" if task == "classification" else "ultralytics",
        "seed": 42,
        "status": status,
        "created_at": "2026-10-29T18:05:00",
        "ended_at": "2026-10-29T18:35:00" if status == "completed" else None,
        "duration_s": 1800.0 if status == "completed" else None,
        "environment": {
            "host": "local",
            "python": "3.11.9",
            "platform": "Windows-11",
            "gpu": None,
            "libraries": {"numpy": "2.1.0"},
        },
        "datasets": [{"name": "plantes", "version": "v3", "root": None}],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _predictions(classes: list[str], n: int, mode: str, rng: np.random.Generator) -> pd.DataFrame:
    if mode == "single":
        probas = rng.dirichlet(np.ones(len(classes)), size=n)
        y_true = [classes[i] for i in rng.integers(0, len(classes), n)]
        y_pred = [classes[i] for i in probas.argmax(axis=1)]
    else:
        probas = rng.random((n, len(classes)))
        y_true = [S.join_labels([c for c in classes if rng.random() < 0.4]) for _ in range(n)]
        y_pred = [S.join_labels([c for c, p in zip(classes, row) if p >= 0.5]) for row in probas]
    df = pd.DataFrame(
        {
            "id": [f"img_{i:04d}" for i in range(n)],
            "group": [f"parcelle_{i % 3}" for i in range(n)],
            "y_true": y_true,
            "y_pred": y_pred,
            "image_path": [f"images/img_{i:04d}.jpg" for i in range(n)],
        }
    )
    for j, c in enumerate(classes):
        df[S.proba_column(c)] = probas[:, j]
    return df


@pytest.fixture
def make_run(tmp_path: Path) -> Callable[..., Path]:
    """Crée un run valide et renvoie son dossier.

    Paramètres : task ("classification" | "detection" | "segmentation"),
    status, classes, label_mode, with_test.
    """

    def _make(
        task: str = "classification",
        status: str = "completed",
        classes: list[str] | None = None,
        label_mode: str = "single",
        with_test: bool = True,
    ) -> Path:
        rng = np.random.default_rng(0)
        run = tmp_path / "runs" / "demo" / RUN_ID
        run.mkdir(parents=True)
        classes = classes or (["sain", "malade"] if task == "classification" else ["feuille", "insecte"])
        binary = task == "classification" and label_mode == "single" and len(classes) == 2

        write_json(run / S.META_FILE, _meta(task, status))
        (run / S.CONFIG_FILE).write_text(
            yaml.safe_dump({"lr": 1e-3, "batch_size": 32, "augment": {"flip": True}}), encoding="utf-8"
        )
        write_json(
            run / S.CLASSES_FILE,
            {"schema_version": 1, "label_mode": label_mode, "classes": classes,
             "positive_class": classes[1] if binary else None},
        )

        epochs = pd.DataFrame(
            {
                "epoch": [0, 1, 2],
                "lr": [1e-3, 5e-4, 1e-4],
                "train_loss": [0.9, 0.6, 0.4],
                "val_loss": [0.95, 0.7, 0.72],
            }
        )
        if task == "classification":
            epochs["val_acc"] = [0.6, 0.75, 0.74]
            epochs[S.per_class_column("val", "recall", classes[0])] = [0.5, 0.7, 0.7]
        else:
            epochs["val_map50"] = [0.3, 0.5, 0.55]
            epochs["val_map50_95"] = [0.1, 0.25, 0.3]
        epochs.to_csv(run / S.EPOCHS_FILE, index=False)

        if task == "classification":
            (run / S.PREDICTIONS_DIR).mkdir()
            _predictions(classes, 40, label_mode, rng).to_csv(run / S.PREDICTIONS_DIR / "val.csv", index=False)
            if with_test and status == "completed":
                _predictions(classes, 20, label_mode, rng).to_csv(
                    run / S.PREDICTIONS_DIR / "test.csv", index=False
                )
        else:
            per_class = [
                {"class": c, "precision": 0.7, "recall": 0.6, "map50": 0.55, "map50_95": 0.3, "n_instances": 10}
                for c in classes
            ]
            summary = {"precision": 0.7, "recall": 0.6, "map50": 0.55, "map50_95": 0.3}
            write_json(
                run / S.DETECTION_DIR / S.DETECTION_METRICS_FILE,
                {"schema_version": 1, "split": "val", "box": summary,
                 "mask": summary if task == "segmentation" else None, "per_class": per_class},
            )
            pd.DataFrame(
                {"class": [classes[0]] * 3, "recall": [0.0, 0.5, 1.0], "precision": [1.0, 0.8, 0.3]}
            ).to_csv(run / S.DETECTION_DIR / S.DETECTION_PR_FILE, index=False)

        (run / S.ARTIFACTS_DIR).mkdir()
        (run / S.ARTIFACTS_DIR / "gradcam.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        write_json(
            run / S.ARTIFACTS_DIR / S.MANIFEST_FILE,
            {"schema_version": 1,
             "items": [{"file": "gradcam.png", "title": "Grad-CAM", "kind": "image"}]},
        )
        (run / S.EXTRA_RESULTS_DIR).mkdir()
        pd.DataFrame({"resolution": [224, 384], "acc": [0.7, 0.75]}).to_csv(
            run / S.EXTRA_RESULTS_DIR / "resolution.csv", index=False
        )
        (run / S.MODEL_DIR).mkdir()
        (run / S.MODEL_DIR / "best.pt").write_bytes(b"0")
        return run

    return _make
