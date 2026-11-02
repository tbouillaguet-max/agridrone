from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from rasterio.transform import from_origin

from agridrone.data.augment import GlobalGain, multispectral_train_transform, rgb_train_transform
from agridrone.data.bands import SensorSpec, load_sensor, select_bands
from agridrone.data.dedup import cluster_ids, dhash, near_duplicate_pairs
from agridrone.data.normalize import compute_band_stats, normalize
from agridrone.data.raster import read_geotiff, read_npy, write_geotiff
from agridrone.data.splits import assert_no_group_leakage, group_split, spatial_split
from agridrone.data.tiling import Window, extract_tile, stitch, tile_windows

# ----------------------------------------------------------------- bandes


def test_select_bands_reorders_by_name(repo_root: Path) -> None:
    rededge = load_sensor(repo_root / "configs/sensors/micasense_rededge.yaml")
    p4m = load_sensor(repo_root / "configs/sensors/dji_p4_multispectral.yaml")
    assert rededge.band_names == ["blue", "green", "red", "nir", "red_edge"]
    image = np.stack([np.full((2, 2), i, np.float32) for i in range(5)])  # bande i = valeur i
    reordered = select_bands(image, rededge, p4m.band_names)
    # Ordre P4M (B, V, R, RE, PIR) : RE est la 5e bande RedEdge, PIR la 4e.
    assert reordered[:, 0, 0].tolist() == [0, 1, 2, 4, 3]
    assert select_bands(image.transpose(1, 2, 0), rededge, ["nir"], channel_axis=-1).shape == (
        2,
        2,
        1,
    )
    with pytest.raises(KeyError):
        select_bands(image, rededge, ["thermal"])
    with pytest.raises(ValueError, match="canaux"):
        select_bands(image[:3], rededge, ["red"])


def test_sensor_validation() -> None:
    with pytest.raises(ValueError, match="double"):
        SensorSpec(name="x", bands=[{"name": "red"}, {"name": "red"}])
    with pytest.raises(ValueError, match="inconnue"):
        SensorSpec(name="x", bands=[{"name": "infrared"}])


# ----------------------------------------------------------------- lecture


def test_geotiff_roundtrip_keeps_georeference_and_mask(tmp_path: Path) -> None:
    data = np.random.default_rng(0).random((5, 20, 30), dtype=np.float32)
    data[:, 0, 0] = np.nan  # pixel invalide
    profile = {"crs": "EPSG:2154", "transform": from_origin(700000, 6600000, 0.05, 0.05)}
    path = write_geotiff(tmp_path / "ortho.tif", data, profile)
    raster = read_geotiff(path)
    assert raster.shape == (5, 20, 30)
    np.testing.assert_allclose(raster.data[:, 1:, 1:], data[:, 1:, 1:])
    assert not raster.valid[0, 0] and raster.valid[1, 1]
    assert raster.profile["crs"].to_epsg() == 2154
    sub = read_geotiff(path, bands=[4, 5])
    np.testing.assert_allclose(sub.data[:, 1:, 1:], data[3:, 1:, 1:])


def test_read_npy_with_alpha(tmp_path: Path) -> None:
    hwc = np.ones((4, 4, 6), np.float32)
    hwc[0, 0, 5] = 0  # alpha nul : pixel invalide
    np.save(tmp_path / "p.npy", hwc)
    raster = read_npy(tmp_path / "p.npy", channel_axis=-1, alpha_channel=5)
    assert raster.data.shape == (5, 4, 4)
    assert not raster.valid[0, 0] and raster.valid.sum() == 15


# ----------------------------------------------------------------- normalisation


def test_band_stats_and_normalization() -> None:
    rng = np.random.default_rng(0)
    data = np.stack([rng.normal(10, 2, (50, 50)), rng.normal(100, 20, (50, 50))]).astype(np.float32)
    valid = np.ones((50, 50), bool)
    stats = compute_band_stats([(data, valid)], ["red", "nir"])
    z = normalize(data, "zscore", stats)
    np.testing.assert_allclose(z.mean(axis=(1, 2)), 0, atol=1e-3)
    np.testing.assert_allclose(z.std(axis=(1, 2)), 1, atol=1e-2)
    p = normalize(data, "percentile", stats)
    assert p.min() >= 0 and p.max() <= 1
    with pytest.raises(ValueError, match="statistiques"):
        normalize(data, "zscore")
    with pytest.raises(ValueError, match="canaux"):
        normalize(data[:1], "zscore", stats)


# ----------------------------------------------------------------- tuilage


@pytest.mark.parametrize(
    ("h", "w", "tile", "overlap"), [(100, 130, 32, 8), (64, 64, 64, 16), (20, 50, 32, 4)]
)
def test_tiles_cover_everything_and_stitch_back(h: int, w: int, tile: int, overlap: int) -> None:
    windows = tile_windows(h, w, tile, overlap)
    coverage = np.zeros((h, w), int)
    for win in windows:
        coverage[win.row : win.row + win.height, win.col : win.col + win.width] += 1
    assert coverage.min() >= 1
    image = np.random.default_rng(1).random((3, h, w), dtype=np.float32)
    tiles = [extract_tile(image, win, tile) for win in windows]
    assert all(t.shape == (3, tile, tile) for t in tiles)
    np.testing.assert_allclose(stitch(tiles, windows, h, w), image, rtol=1e-6)


def test_tile_overlap_and_errors() -> None:
    windows = tile_windows(100, 100, 40, 10)
    cols = sorted({w.col for w in windows})
    assert cols == [0, 30, 60]  # pas de 30, dernière tuile recalée sur le bord
    with pytest.raises(ValueError):
        tile_windows(10, 10, 8, 8)


# ----------------------------------------------------------------- découpage


def test_group_split_keeps_groups_together_and_is_reproducible() -> None:
    groups = [f"g{i // 7}" for i in range(700)]  # 100 groupes de 7
    fractions = {"train": 0.7, "val": 0.15, "test": 0.15}
    splits = group_split(groups, fractions, seed=3)
    assert_no_group_leakage(groups, splits)
    counts = {s: splits.count(s) / len(splits) for s in fractions}
    assert all(abs(counts[s] - fractions[s]) < 0.03 for s in fractions)
    assert group_split(groups, fractions, seed=3) == splits
    assert group_split(groups, fractions, seed=4) != splits
    with pytest.raises(AssertionError):
        assert_no_group_leakage(["a", "a"], ["train", "test"])
    with pytest.raises(ValueError):
        group_split(groups, {"train": 0.5, "test": 0.4})


def test_spatial_split_never_shares_pixels_between_splits() -> None:
    windows = tile_windows(400, 600, 64, 16)
    splits = spatial_split(
        windows, block=128, fractions={"train": 0.6, "val": 0.2, "test": 0.2}, seed=0
    )
    owner = np.full((400, 600), "", dtype=object)
    for win, split in zip(windows, splits, strict=True):
        if split is None:
            continue
        region = owner[win.row : win.row + win.height, win.col : win.col + win.width]
        assert set(np.unique(region)) <= {"", split}, "pixel partagé entre deux ensembles"
        region[:] = split
    kept = [s for s in splits if s is not None]
    assert {"train", "val", "test"} <= set(kept)
    assert len(kept) > 0.5 * len(windows)
    with pytest.raises(ValueError):
        spatial_split([Window(0, 0, 64, 64)], block=32, fractions={"train": 1.0})


# ----------------------------------------------------------------- doublons


def _jpeg(img: Image.Image, quality: int) -> Image.Image:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf)


def test_dhash_finds_resized_and_recompressed_copies() -> None:
    rng = np.random.default_rng(0)
    base = Image.fromarray((rng.random((64, 64, 3)) * 255).astype(np.uint8)).resize((256, 256))
    copy = _jpeg(base.resize((180, 180)), quality=60)
    other = Image.fromarray((rng.random((64, 64, 3)) * 255).astype(np.uint8)).resize((256, 256))
    hashes = np.array([dhash(base), dhash(copy), dhash(other)], dtype=np.uint64)
    pairs = near_duplicate_pairs(hashes, max_distance=6)
    assert [(i, j) for i, j, _ in pairs] == [(0, 1)]
    assert cluster_ids(3, pairs) == [0, 0, 2]


# ----------------------------------------------------------------- augmentations


@pytest.mark.parametrize("channels", [4, 5, 6])
def test_multispectral_augmentation_preserves_band_ratios(channels: int) -> None:
    values = np.linspace(0.05, 0.6, channels, dtype=np.float32)
    image = np.ones((96, 96, channels), np.float32) * values
    transform = multispectral_train_transform(seed=7)
    for _ in range(10):
        out = transform(image=image, mask=np.zeros((96, 96), np.uint8))["image"]
        assert out.shape == image.shape and out.dtype == np.float32
        inner = out[16:-16, 16:-16]
        ratios = inner / inner[..., :1]
        np.testing.assert_allclose(
            ratios, np.broadcast_to(values / values[0], ratios.shape), rtol=1e-4
        )


def test_multispectral_augmentation_keeps_mask_aligned() -> None:
    image = np.zeros((64, 64, 5), np.float32)
    image[10:20, 30:40, :] = 0.8  # objet visible sur toutes les bandes
    mask = (image[..., 0] > 0).astype(np.uint8)
    transform = multispectral_train_transform(seed=1)
    for _ in range(10):
        out = transform(image=image, mask=mask)
        bright = out["image"][..., 0] > 0.4
        overlap = (bright & (out["mask"] == 1)).sum() / max(bright.sum(), 1)
        assert overlap > 0.8


def test_global_gain_and_rgb_pipeline() -> None:
    image = np.full((8, 8, 5), 0.5, np.float32)
    out = GlobalGain(gain_range=(1.5, 1.5), p=1)(image=image)["image"]
    np.testing.assert_allclose(out, 0.75)
    rgb = (np.random.default_rng(0).random((300, 400, 3)) * 255).astype(np.uint8)
    assert rgb_train_transform(224, seed=0)(image=rgb)["image"].shape == (224, 224, 3)
