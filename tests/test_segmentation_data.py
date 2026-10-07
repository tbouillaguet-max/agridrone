from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from agridrone.data.bands import load_sensor
from agridrone.data.raster import read_geotiff, write_geotiff
from agridrone.data.segmentation import (
    IGNORE_INDEX,
    WEEDSGALORE_BAND_FILES,
    convert_weedsgalore,
    remap,
    tile_orthomosaic,
)


def test_remap_marks_unknown_values_as_ignored() -> None:
    mask = np.array([[0, 1, 2], [5, 9, 3]], np.uint8)
    out = remap(mask, {0: 0, 1: 1, 2: 2, 3: 2, 5: 2})
    assert out.tolist() == [[0, 1, 2], [2, IGNORE_INDEX, 2]]


def _fake_weedsgalore(root: Path) -> None:
    rng = np.random.default_rng(0)
    (root / "splits").mkdir(parents=True)
    samples = {
        "train": ["2023-05-25_0001", "2023-05-30_0002"],
        "val": ["2023-05-25_0003"],
        "test": ["2023-05-30_0004"],
    }
    for split, ids in samples.items():
        (root / "splits" / f"{split}.txt").write_text("\n".join(ids) + "\n")
        for sample in ids:
            date = sample.rsplit("_", 1)[0]
            (root / date / "images").mkdir(parents=True, exist_ok=True)
            (root / date / "semantics").mkdir(parents=True, exist_ok=True)
            for k, suffix in enumerate(WEEDSGALORE_BAND_FILES.values()):
                band = np.full((8, 8), 1000 * (k + 1), np.uint16) + rng.integers(
                    0, 10, (8, 8), dtype=np.uint16
                )
                Image.fromarray(band).save(root / date / "images" / f"{sample}_{suffix}.png")
            mask = np.zeros((8, 8), np.uint8)
            mask[:2] = 1
            mask[6:, :4] = 4
            Image.fromarray(mask).save(root / date / "semantics" / f"{sample}.png")


def test_convert_weedsgalore_keeps_official_split_and_band_order(
    tmp_path: Path, repo_root: Path
) -> None:
    root = tmp_path / "wg"
    _fake_weedsgalore(root)
    sensor = load_sensor(repo_root / "configs/sensors/dji_p4_multispectral.yaml")
    out = tmp_path / "out"
    df = convert_weedsgalore(
        root,
        out,
        sensor,
        ["background", "crop", "weed"],
        {0: 0, 1: 1, 2: 2, 3: 2, 4: 2, 5: 2},
        {"license": "CC-BY-4.0"},
    )
    assert df.set_index("sample")["split"].to_dict() == {
        "2023-05-25_0001": "train",
        "2023-05-30_0002": "train",
        "2023-05-25_0003": "val",
        "2023-05-30_0004": "test",
    }
    image = np.load(out / "images" / "2023-05-25_0001.npy")
    assert image.shape == (5, 8, 8) and image.dtype == np.float32
    # Fichiers synthétiques : B=1000, G=2000, R=3000, RE=4000, NIR=5000 (+ bruit < 10).
    assert np.round(image.mean(axis=(1, 2)) * 65535 / 1000).tolist() == [1, 2, 3, 4, 5]

    # Avec un capteur rangé B, V, R, PIR, RE, la conversion suit les noms de bandes.
    rededge = load_sensor(repo_root / "configs/sensors/micasense_rededge.yaml")
    out2 = tmp_path / "out2"
    convert_weedsgalore(root, out2, rededge, ["background", "crop", "weed"], {0: 0, 1: 1, 4: 2}, {})
    image2 = np.load(out2 / "images" / "2023-05-25_0001.npy")
    assert np.round(image2.mean(axis=(1, 2)) * 65535 / 1000).tolist() == [1, 2, 3, 5, 4]
    mask = np.asarray(Image.open(out / "masks" / "2023-05-25_0001.png"))
    assert set(np.unique(mask)) == {0, 1, 2}
    info = json.loads((out / "dataset.json").read_text())
    assert info["bands"] == sensor.band_names and info["classes"] == ["background", "crop", "weed"]


def test_tile_orthomosaic_georeferenced_and_spatially_split(tmp_path: Path) -> None:
    data = np.random.default_rng(0).random((5, 300, 400), dtype=np.float32)
    data[:, :, :60] = np.nan  # bande sans donnée (bord d'orthomosaïque)
    transform = from_origin(500000, 5000000, 0.02, 0.02)
    ortho = write_geotiff(
        tmp_path / "ortho.tif", data, {"crs": "EPSG:32631", "transform": transform}
    )

    df = tile_orthomosaic(
        ortho,
        tmp_path / "tiles",
        tile=64,
        overlap=16,
        block=128,
        fractions={"train": 0.6, "val": 0.2, "test": 0.2},
        seed=0,
    )
    assert set(df["split"]) <= {"train", "val", "test"} and len(df) > 10
    assert (df["valid_fraction"] >= 0.5).all()  # tuiles du bord sans donnée écartées
    first = df.iloc[0]
    tile_path = tmp_path / "tiles" / first["split"] / f"{first['tile']}.tif"
    tile = read_geotiff(tile_path)
    np.testing.assert_allclose(
        tile.data, data[:, first["row"] : first["row"] + 64, first["col"] : first["col"] + 64]
    )
    with rasterio.open(tile_path) as ds:  # coin haut-gauche de la tuile dans le repère de l'ortho
        assert ds.transform.c == transform.c + first["col"] * 0.02
        assert ds.transform.f == transform.f - first["row"] * 0.02
    index = pd.read_csv(tmp_path / "tiles" / "ortho_tiles.csv")
    assert len(index) == len(df)
