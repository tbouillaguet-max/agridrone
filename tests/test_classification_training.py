from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
import yaml
from PIL import Image

from agridrone.cli import main
from agridrone.core.config import ConfigError, validate_config
from agridrone.data.datasets import classification_split, load_rgb
from agridrone.models.classifier import ClassifierCheckpoint
from agridrone.training.common import balanced_class_weights, warmup_cosine

# fork() d'un processus multi-threadé (workers du DataLoader) : bénin ici.
pytestmark = pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded:DeprecationWarning"
)


def test_warmup_cosine_schedule() -> None:
    f = warmup_cosine(warmup_steps=4, total_steps=20, min_ratio=0.1)
    assert f(0) == pytest.approx(0.25) and f(3) == pytest.approx(1.0)
    after = [f(s) for s in range(4, 21)]
    assert all(a >= b for a, b in pairwise(after))
    assert f(20) == pytest.approx(0.1)
    with pytest.raises(ValueError):
        warmup_cosine(30, 20)


def test_balanced_class_weights() -> None:
    w = balanced_class_weights([0, 0, 0, 1], 2)
    assert w.tolist() == pytest.approx([4 / 6, 2.0])
    with pytest.raises(ValueError, match="sans aucune image"):
        balanced_class_weights([0, 0], 2)


def test_load_rgb_uses_reduced_jpeg_decoding_and_exif_orientation(tmp_path: Path) -> None:
    path = tmp_path / "big.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation : rotation de 90°
    Image.new("RGB", (1600, 1200), (10, 200, 30)).save(path, exif=exif)
    image = load_rgb(path, min_size=200)
    # Décodage au 1/4 (400×300) puis rotation : portrait 300×400.
    assert image.shape == (400, 300, 3) and image.dtype == np.uint8
    assert load_rgb(path).shape == (1600, 1200, 3)


def _make_dataset(root: Path) -> Path:
    data = root / "processed"
    rng = np.random.default_rng(0)
    rows = []
    for split, n in {"train": 12, "val": 8, "test": 6, "test_other": 4}.items():
        for i in range(n):
            label = "rust" if (i % 2 or split == "test_other") else "healthy"
            base = np.array([200, 90, 30] if label == "rust" else [40, 160, 50], np.float32)
            pixels = np.clip(base + rng.normal(0, 25, (48, 64, 3)), 0, 255).astype(np.uint8)
            file = f"{split}/{label}/img{i}.{'png' if i % 3 == 0 else 'jpg'}"
            (data / file).parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(pixels).save(data / file)
            rows.append({"file": file, "split": split, "label": label, "excluded_reason": ""})
    rows.append({"file": "", "split": "", "label": "rust", "excluded_reason": "doublon exact"})
    pd.DataFrame(rows).to_csv(data / "manifest.csv", index=False)
    return data


def _raw_config(tmp_path: Path, data: Path) -> dict[str, object]:
    return {
        "task": "classification",
        "name": "tiny",
        "seed": 3,
        "device": "cpu",
        "num_workers": 0,
        "paths": {"runs": str(tmp_path / "runs")},
        "tracking": {"enabled": False},
        "data": {
            "dir": str(data),
            "classes": ["healthy", "rust"],
            "display_names": {"healthy": "sain"},
            "test_splits": ["test", "test_other"],
            "split_names": {"test_other": "autre source"},
        },
        "model": {"arch": "mobilenetv3_small_050", "pretrained": False, "input_size": 32},
        "train": {"epochs": 2, "batch_size": 4, "patience": None},
        "eval": {"batch_size": 8, "target_coverage": 0.75, "max_missed_rate": 0.0},
    }


def test_classification_split_checks_classes(tmp_path: Path) -> None:
    data = _make_dataset(tmp_path)
    manifest = pd.read_csv(data / "manifest.csv", keep_default_na=False)
    files, labels = classification_split(manifest, data, "val", ["healthy", "rust"])
    assert len(files) == 8 and set(labels) == {0, 1} and all(f.is_file() for f in files)
    with pytest.raises(ValueError, match="classes absentes"):
        classification_split(manifest, data, "val", ["healthy"])
    with pytest.raises(ValueError, match="vide ou absent"):
        classification_split(manifest, data, "nope", ["healthy", "rust"])


def test_config_validation() -> None:
    raw = _raw_config(Path("/tmp"), Path("/tmp"))
    with pytest.raises(ConfigError, match="healthy_class"):
        validate_config({**raw, "data": {"classes": ["a", "b"]}})
    with pytest.raises(ConfigError):
        validate_config({**raw, "train": {"precision": "fp16"}})
    data = dict(raw["data"])  # type: ignore[call-overload]
    with pytest.raises(ConfigError, match="split_names"):
        validate_config({**raw, "data": {**data, "split_names": {"nope": "x"}}})


def test_train_then_evaluate_end_to_end(tmp_path: Path) -> None:
    from agridrone.training.classification import (
        _split_loader,
        evaluate,
        predict,
        read_manifest,
        train,
    )

    data = _make_dataset(tmp_path)
    cfg = validate_config(_raw_config(tmp_path, data))
    run_dir = train(cfg, root=tmp_path)

    for name in ("best.pt", "history.csv", "history.png", "config.yaml", "environment.json"):
        assert (run_dir / name).is_file(), name
    history = pd.read_csv(run_dir / "history.csv")
    assert len(history) == 2 and history["lr"].iloc[1] > 0
    metrics = json.loads((run_dir / "eval" / "metrics.json").read_text())
    assert set(metrics["splits"]) == {"val", "test", "test_other"}
    for split in metrics["splits"]:
        for fig in ("confusion_argmax.png", "confusion_decision.png", "predictions.csv"):
            assert (run_dir / "eval" / split / fig).is_file()
    assert (run_dir / "eval" / "risk_coverage.png").is_file()
    other = metrics["splits"]["test_other"]["argmax"]["per_class"]["healthy"]
    assert other["support"] == 0 and other["recall"] is None  # classe absente de ce test

    # Le checkpoint se recharge sans exécution de code et porte sa règle de décision.
    ckpt = ClassifierCheckpoint.load(run_dir / "best.pt")
    assert ckpt.classes == ["healthy", "rust"] and ckpt.decision == metrics["decision_rule"]
    predictions = pd.read_csv(run_dir / "eval" / "val" / "predictions.csv")
    cpu = torch.device("cpu")
    _, loader = _split_loader(cfg, read_manifest(data), data, "val", ckpt, cpu)
    probs, _ = predict(ckpt.build_model(), loader, cpu, "fp32")
    np.testing.assert_allclose(probs[:, 1], predictions["p_rust"], atol=1e-5)

    # Réévaluation : mêmes résultats, checkpoint inchangé.
    again = evaluate(cfg, run_dir, out_dir=tmp_path / "re", root=tmp_path)
    assert again["decision_rule"] == metrics["decision_rule"]
    assert again["splits"]["test"]["argmax"] == metrics["splits"]["test"]["argmax"]


def test_cli_train_is_reproducible(tmp_path: Path) -> None:
    data = _make_dataset(tmp_path)
    raw = _raw_config(tmp_path, data)
    config = tmp_path / "tiny.yaml"
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")

    runs = []
    for _ in range(2):
        assert main(["train", "-c", str(config), "train.epochs=1"]) == 0
        runs = sorted((tmp_path / "runs" / "classification").iterdir())
    first, second = (pd.read_csv(r / "history.csv") for r in runs)
    np.testing.assert_allclose(first["train_loss"], second["train_loss"], rtol=1e-6)
    np.testing.assert_allclose(first["val_loss"], second["val_loss"], rtol=1e-6)

    assert main(["evaluate", "--run", str(runs[0]), "--out", str(tmp_path / "ev")]) == 0
    assert (tmp_path / "ev" / "metrics.json").is_file()
    assert main(["evaluate", "--run", str(tmp_path)]) == 2  # pas un dossier de run
