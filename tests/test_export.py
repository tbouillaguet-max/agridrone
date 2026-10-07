from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from agridrone.models.classifier import ClassifierCheckpoint, build_classifier
from agridrone.models.segmenter import SegmenterCheckpoint, build_unet

pytest.importorskip("onnxruntime")
pytestmark = pytest.mark.slow  # export dynamo : quelques secondes par modèle


def test_classifier_export_matches_pytorch(tmp_path: Path) -> None:
    from agridrone.export.onnx import benchmark, export_classifier, max_difference

    model = build_classifier("mobilenetv3_small_050", 3)
    ckpt = ClassifierCheckpoint.from_model(
        model,
        arch="mobilenetv3_small_050",
        classes=["healthy", "rust", "septoria"],
        input_size=64,
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
        decision={"tau": 0.5, "tau_healthy": 0.8, "healthy_index": 0},
    )
    path, wrapped = export_classifier(ckpt, tmp_path)
    rng = np.random.default_rng(0)
    inputs = [rng.random((n, 3, 64, 64), dtype=np.float32) for n in (1, 3)]  # lot dynamique
    assert max_difference(path, wrapped, inputs) < 1e-4

    meta = json.loads((tmp_path / "model.json").read_text())
    assert meta["classes"] == ckpt.classes and meta["decision"]["tau_healthy"] == 0.8
    rows = benchmark(path, wrapped, (3, 64, 64), [1, 2], repeat=2)
    assert len(rows) == 4 and all(r["images_per_second"] > 0 for r in rows)


def test_segmenter_export_accepts_any_multiple_of_32(tmp_path: Path) -> None:
    from agridrone.export.onnx import export_segmenter, max_difference

    bands = ["green", "red", "red_edge", "nir"]
    ckpt = SegmenterCheckpoint.from_model(
        build_unet("tu-resnet18", len(bands), 3),
        encoder="tu-resnet18",
        bands=bands,
        classes=["background", "crop", "weed"],
        mean=[0.4] * 4,
        std=[0.1] * 4,
        tile=64,
        overlap=16,
    )
    path, wrapped = export_segmenter(ckpt, tmp_path)
    rng = np.random.default_rng(1)
    inputs = [rng.random(shape, dtype=np.float32) for shape in [(1, 4, 64, 64), (2, 4, 96, 128)]]
    assert max_difference(path, wrapped, inputs) < 1e-4
    meta = json.loads((tmp_path / "model.json").read_text())
    assert meta["input"]["bands"] == bands and meta["input"]["tiling"]["tile"] == 64


def test_cli_export_run(tmp_path: Path) -> None:
    from agridrone.cli import main

    model = build_classifier("mobilenetv3_small_050", 2)
    run = tmp_path / "run"
    ClassifierCheckpoint.from_model(
        model,
        arch="mobilenetv3_small_050",
        classes=["healthy", "rust"],
        input_size=64,
        mean=[0.5] * 3,
        std=[0.2] * 3,
    ).save(run / "best.pt")
    assert main(["export", "--run", str(run), "--repeat", "2"]) == 0
    report = json.loads((run / "export" / "benchmark.json").read_text())
    assert report["max_abs_diff_onnx_vs_pytorch"] < 1e-4 and report["gflops_per_input"] > 0
    assert {r["runtime"].split()[0] for r in report["benchmark"]} == {"PyTorch", "ONNX"}
    assert main(["export", "--run", str(tmp_path)]) == 2  # pas de best.pt
