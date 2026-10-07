from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from PIL import Image

from agridrone.core.config import ConfigError, validate_config
from agridrone.data.augment import multispectral_train_transform
from agridrone.data.datasets import SegmentationDataset, load_segmentation_sample
from agridrone.data.normalize import BandStats
from agridrone.models.segmenter import SegmenterCheckpoint

pytestmark = pytest.mark.filterwarnings(
    "ignore:This process .* is multi-threaded:DeprecationWarning"
)

BANDS = ["blue", "green", "red", "red_edge", "nir"]
# Réflectances typiques (B, V, R, RE, PIR) : sol, culture (PIR fort), adventice.
SIGNATURES = {
    0: [0.30, 0.32, 0.35, 0.38, 0.40],
    1: [0.05, 0.12, 0.05, 0.35, 0.70],
    2: [0.08, 0.15, 0.10, 0.30, 0.45],
}


def _make_dataset(root: Path, size: int = 64) -> Path:
    data = root / "weeds"
    (data / "images").mkdir(parents=True)
    (data / "masks").mkdir()
    rng = np.random.default_rng(0)
    rows = []
    for i, split in enumerate(["train"] * 6 + ["val"] * 2 + ["test"] * 2):
        mask = np.zeros((size, size), np.uint8)
        for cls in (1, 2):
            for _ in range(3):
                r, c = rng.integers(4, size - 12, 2)
                mask[r : r + 8, c : c + 8] = cls
        mask[0, 0] = 255  # pixel non annoté
        image = np.stack(
            [np.choose(mask % 255, [s[b] for s in SIGNATURES.values()]) for b in range(5)]
        )
        image = np.clip(image + rng.normal(0, 0.02, image.shape), 0, 1).astype(np.float32)
        name = f"s{i:02d}"
        np.save(data / "images" / f"{name}.npy", image)
        Image.fromarray(mask).save(data / "masks" / f"{name}.png")
        rows.append({"sample": name, "split": split})
    pd.DataFrame(rows).to_csv(data / "index.csv", index=False)
    (data / "dataset.json").write_text(
        json.dumps({"bands": BANDS, "classes": ["background", "crop", "weed"]})
    )
    train = [np.load(data / "images" / f"{r['sample']}.npy") for r in rows if r["split"] == "train"]
    stacked = np.concatenate([t.reshape(5, -1) for t in train], axis=1)
    BandStats(
        bands=BANDS,
        mean=stacked.mean(axis=1).tolist(),
        std=stacked.std(axis=1).tolist(),
        p_low=[0.0] * 5,
        p_high=[1.0] * 5,
        percentiles=(2.0, 98.0),
        n_pixels=stacked.shape[1],
    ).save(data / "band_stats_train.json")
    return data


def _raw_config(tmp_path: Path, data: Path, **data_extra: object) -> dict[str, object]:
    return {
        "task": "segmentation",
        "name": "tiny",
        "seed": 1,
        "device": "cpu",
        "num_workers": 0,
        "paths": {"runs": str(tmp_path / "runs")},
        "tracking": {"enabled": False},
        "data": {"dir": str(data), **data_extra},
        "model": {"encoder": "tu-resnet18", "pretrained": False},
        "train": {"epochs": 2, "batch_size": 4, "crop": 32, "samples_per_image": 2},
        "eval": {"tile": 32, "overlap": 8, "examples": 2},
    }


def test_segmentation_dataset_crops_and_selects_bands(tmp_path: Path) -> None:
    data = _make_dataset(tmp_path)
    image, mask = load_segmentation_sample(data, "s00")
    assert image.shape == (5, 64, 64) and mask.shape == (64, 64) and mask[0, 0] == 255
    dataset = SegmentationDataset(
        data,
        ["s00", "s01"],
        band_indices=[4, 2],  # PIR puis R
        mean=[0.5, 0.2],
        std=[0.2, 0.1],
        transform=multispectral_train_transform(crop=32, seed=0),
        samples_per_image=3,
    )
    assert len(dataset) == 6
    x, y = dataset[4]
    assert x.shape == (2, 32, 32) and x.dtype == torch.float32
    assert y.shape == (32, 32) and y.dtype == torch.long
    assert set(np.unique(y.numpy())) <= {0, 1, 2, 255}

    full = SegmentationDataset(data, ["s00"], [0, 1, 2, 3, 4], mean=[0.0] * 5, std=[1.0] * 5)
    x, y = full[0]
    np.testing.assert_allclose(x.numpy(), image, rtol=1e-6)  # sans transformation : identique


def test_zoom_out_borders_are_ignored_not_background() -> None:
    transform = multispectral_train_transform(scale=(0.5, 0.5), seed=0)
    image = np.full((64, 64, 5), 0.5, np.float32)
    mask = np.ones((64, 64), np.uint8)
    for _ in range(20):  # l'Affine s'applique avec p = 0.5
        out = transform(image=image, mask=mask)
        if (out["mask"] != 1).any():
            break
    assert set(np.unique(out["mask"])) == {1, 255}


def test_segmentation_config_validation(tmp_path: Path) -> None:
    raw = _raw_config(tmp_path, tmp_path)
    with pytest.raises(ConfigError, match="multiple de 32"):
        validate_config({**raw, "train": {"crop": 50}})


def test_train_unet_with_index_baselines(tmp_path: Path) -> None:
    from agridrone.training.segmentation import evaluate, train

    data = _make_dataset(tmp_path)
    cfg = validate_config(_raw_config(tmp_path, data, bands=["red", "nir", "red_edge"]))
    run_dir = train(cfg, root=tmp_path)

    for name in ("best.pt", "history.csv", "history.png", "eval/metrics.json", "eval/iou_test.png"):
        assert (run_dir / name).is_file(), name
    assert (run_dir / "eval" / "exemples_val.png").is_file()
    metrics = json.loads((run_dir / "eval" / "metrics.json").read_text())
    assert metrics["bands"] == ["red", "nir", "red_edge"]
    test = metrics["splits"]["test"]
    assert set(test["baselines"]) == {
        "ndvi_otsu",
        "ndvi_seuil_supervise",
        "ndvi_multi_otsu",
        "ndre_otsu",
        "ndre_seuil_supervise",
        "ndre_multi_otsu",
    }
    # Données synthétiques bien séparées par le NDVI : la baseline supervisée y excelle.
    veg = test["baselines"]["ndvi_seuil_supervise"]["fond_vegetation"]["per_class"]["végétation"]
    assert veg["iou"] > 0.9
    assert "classes" not in test["baselines"]["ndvi_otsu"]  # binaire : fond / végétation
    assert test["unet"]["classes"]["miou"] is not None

    ckpt = SegmenterCheckpoint.load(run_dir / "best.pt")
    assert ckpt.bands == ["red", "nir", "red_edge"] and ckpt.tile == 32
    again = evaluate(cfg, run_dir, out_dir=tmp_path / "re", root=tmp_path)
    assert again["splits"]["test"]["unet"] == {
        **metrics["splits"]["test"]["unet"],
        "seconds": again["splits"]["test"]["unet"]["seconds"],
    }
