from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

from agridrone.eval.segmentation import (
    merge_confusion,
    pixel_confusion,
    plot_examples,
    plot_iou_comparison,
    segmentation_scores,
)
from agridrone.models.indices import (
    IndexBaseline,
    best_supervised_threshold,
    compute_index,
    fit_index_baselines,
    index_histogram,
    multi_otsu_thresholds,
    normalized_difference,
    otsu_threshold,
)
from agridrone.models.segmenter import SegmenterCheckpoint, build_unet, predict_tiled

DJI = ["blue", "green", "red", "red_edge", "nir"]
REDEDGE = ["blue", "green", "red", "nir", "red_edge"]


def test_normalized_difference_and_named_bands() -> None:
    nd = normalized_difference(np.array([0.6, 0.0, 0.5]), np.array([0.2, 0.0, 0.5]))
    assert nd[0] == pytest.approx(0.5) and np.isnan(nd[1]) and nd[2] == 0.0

    rng = np.random.default_rng(0)
    dji = rng.random((5, 4, 4)).astype(np.float32)
    rededge = dji[[0, 1, 2, 4, 3]]  # même scène, ordre de stockage MicaSense
    for index in ("ndvi", "ndre"):
        np.testing.assert_allclose(
            compute_index(dji, DJI, index), compute_index(rededge, REDEDGE, index)
        )
    with pytest.raises(ValueError, match="absentes"):
        compute_index(dji[:3], ["blue", "green", "red"], "ndvi")


def test_otsu_finds_the_valley_between_modes() -> None:
    rng = np.random.default_rng(1)
    bimodal = np.concatenate([rng.normal(-0.5, 0.08, 5000), rng.normal(0.4, 0.08, 3000)])
    t = otsu_threshold(index_histogram(bimodal))
    assert -0.2 < t < 0.1

    trimodal = np.concatenate(
        [rng.normal(-0.6, 0.05, 4000), rng.normal(0.0, 0.05, 2000), rng.normal(0.6, 0.05, 3000)]
    )
    t1, t2 = multi_otsu_thresholds(index_histogram(trimodal))
    assert -0.5 < t1 < -0.1 and 0.1 < t2 < 0.5


def test_index_baseline_predicts_intervals() -> None:
    baseline = IndexBaseline("ndvi", (0.0, 0.5), (0, 2, 1), "multi_otsu")
    # PIR et R choisis pour donner NDVI = -0.5, 0.2, 0.8 et un pixel indéfini (0 / 0).
    nir = np.array([[0.25, 0.6, 0.9, 0.0]])
    red = np.array([[0.75, 0.4, 0.1, 0.0]])
    image = np.zeros((5, 1, 4), np.float32)
    image[DJI.index("nir")], image[DJI.index("red")] = nir, red
    assert baseline.predict(image, DJI, nodata=0).tolist() == [[0, 2, 1, 0]]
    with pytest.raises(ValueError):
        IndexBaseline("ndvi", (0.5, 0.0), (0, 1, 2), "x")


def test_supervised_threshold_and_fitted_baselines() -> None:
    rng = np.random.default_rng(2)
    soil = index_histogram(rng.normal(-0.3, 0.05, 6000))
    crop = index_histogram(rng.normal(0.6, 0.05, 2000))
    weed = index_histogram(rng.normal(0.25, 0.05, 1500))
    t, iou = best_supervised_threshold(crop + weed, soil)
    assert -0.15 < t < 0.15 and iou > 0.99

    fitted = fit_index_baselines(
        np.stack([soil, crop, weed]), "ndvi", background=0, vegetation=[1, 2]
    )
    assert set(fitted) == {"ndvi_otsu", "ndvi_seuil_supervise", "ndvi_multi_otsu"}
    multi = fitted["ndvi_multi_otsu"]
    assert multi.labels == (0, 2, 1)  # l'adventice (NDVI plus bas) avant la culture


def test_pixel_metrics_ignore_and_merge() -> None:
    truth = np.array([[0, 0, 1, 2], [2, 255, 1, 1]])
    pred = np.array([[0, 1, 1, 2], [1, 0, 1, 0]])
    cm = pixel_confusion(truth, pred, 3)
    assert cm.sum() == 7  # le pixel 255 est ignoré
    assert cm.tolist() == [[1, 1, 0], [1, 2, 0], [0, 1, 1]]
    scores = segmentation_scores(cm, ["fond", "culture", "adventice"])
    culture = scores["per_class"]["culture"]
    assert culture["iou"] == pytest.approx(2 / 5) and culture["f1"] == pytest.approx(4 / 7)
    assert scores["pixel_accuracy"] == pytest.approx(4 / 7)

    merged = merge_confusion(cm, [[0], [1, 2]])
    assert merged.tolist() == [[1, 1], [1, 4]]
    absent = segmentation_scores(np.array([[3, 0], [0, 0]]), ["a", "b"])
    assert absent["per_class"]["b"]["iou"] is None and absent["miou"] == 1.0
    with pytest.raises(ValueError):
        merge_confusion(cm, [[0], [1]])


def test_predict_tiled_matches_full_image_for_pointwise_model() -> None:
    model = nn.Conv2d(5, 3, kernel_size=1)
    image = np.random.default_rng(3).normal(size=(5, 100, 130)).astype(np.float32)
    probs = predict_tiled(
        model, image, tile=64, overlap=16, device=torch.device("cpu"), batch_size=3
    )
    with torch.no_grad():
        full = torch.softmax(model(torch.from_numpy(image)[None]), dim=1)[0].numpy()
    assert probs.shape == (3, 100, 130)
    np.testing.assert_allclose(probs, full, atol=1e-5)
    with pytest.raises(ValueError, match="multiple de 32"):
        predict_tiled(model, image, tile=50, overlap=0, device=torch.device("cpu"))


def test_segmenter_checkpoint_round_trip(tmp_path: Path) -> None:
    model = build_unet("tu-resnet18", in_channels=4, num_classes=3)
    ckpt = SegmenterCheckpoint.from_model(
        model,
        encoder="tu-resnet18",
        bands=["green", "red", "red_edge", "nir"],
        classes=["a", "b", "c"],
        mean=[0.5] * 4,
        std=[0.1] * 4,
        tile=64,
        overlap=16,
    )
    loaded = SegmenterCheckpoint.load(ckpt.save(tmp_path / "s.pt"))
    rebuilt = loaded.build_model()
    x = torch.randn(1, 4, 64, 64)
    model.eval()
    with torch.no_grad():
        torch.testing.assert_close(rebuilt(x), model(x))
    normalized = loaded.normalize(np.full((4, 2, 2), 0.6, np.float32))
    np.testing.assert_allclose(normalized, 1.0, rtol=1e-5)


def test_segmentation_figures(tmp_path: Path) -> None:
    bars = {"U-Net": {"fond": 0.9, "culture": 0.5}, "NDVI": {"fond": 0.8, "culture": None}}
    assert plot_iou_comparison(bars, ["fond", "culture"], tmp_path / "iou.png", title="t").is_file()
    rows = [
        {"image": np.random.default_rng(0).random((8, 8, 3)), "masque": np.eye(8, dtype=np.uint8)}
    ]
    path = plot_examples(
        rows,
        ["image", "masque"],
        ["#d8d2c4", "#1baf7a"],
        ["fond", "culture"],
        tmp_path / "ex.png",
        title="t",
    )
    assert path.stat().st_size > 1000
