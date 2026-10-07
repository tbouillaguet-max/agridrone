from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from agridrone.data.classification import (
    ClassificationDataConfig,
    SourceSpec,
    add_fingerprints,
    assign_splits,
    materialize,
    raw_label,
    scan_sources,
)
from agridrone.data.splits import assert_no_group_leakage


def _image(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    return Image.fromarray((rng.random((24, 24, 3)) * 255).astype(np.uint8)).resize((96, 96))


def _save(img: Image.Image, path: Path, day: str | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = Image.Exif()
    if day:
        exif[306] = f"{day} 10:00:00"
    img.save(path, quality=95, exif=exif)
    return path


@pytest.fixture
def interim(tmp_path: Path) -> Path:
    root = tmp_path / "interim"
    # Source d'entraînement : 2 classes, 3 jours de prise de vue.
    for i in range(30):
        cls = "Rust" if i % 2 else "Healthy"
        day = f"2023:05:0{1 + i % 3}"
        _save(_image(i), root / "train_src" / "data" / cls / f"{cls}{i}.jpg", day)
    _save(_image(100), root / "train_src" / "data" / "Mystery" / "m.jpg")  # classe non prévue
    # Source de test : une copie exacte, une copie redimensionnée, et des images nouvelles.
    (root / "test_src" / "healthy").mkdir(parents=True)
    (root / "test_src" / "healthy" / "copy.jpg").write_bytes(
        (root / "train_src/data/Healthy/Healthy0.jpg").read_bytes()
    )
    _save(
        Image.open(root / "train_src/data/Rust/Rust1.jpg").resize((80, 80)),
        root / "test_src" / "rust" / "resized.jpg",
    )
    for i in range(200, 210):
        _save(_image(i), root / "test_src" / ("rust" if i % 2 else "healthy") / f"new{i}.jpg")
    return root


@pytest.fixture
def cfg() -> ClassificationDataConfig:
    return ClassificationDataConfig(
        classes=["healthy", "rust"],
        fractions={"train": 0.6, "val": 0.2, "test": 0.2},
        sources={
            "train_src": SourceSpec(
                root="data", mapping={"Healthy": "healthy", "Rust": "rust"}, role="train"
            ),
            "test_src": SourceSpec(mapping={"healthy": "healthy", "rust": "rust"}, role="test"),
        },
    )


def test_prepare_classification_end_to_end(
    interim: Path, cfg: ClassificationDataConfig, tmp_path: Path
) -> None:
    df = assign_splits(add_fingerprints(scan_sources(cfg, interim), interim, workers=2), cfg)
    reasons = df.set_index(df["path"].str.split("/").str[-1])["excluded_reason"]

    assert reasons["copy.jpg"] == "doublon exact"
    assert reasons["resized.jpg"] == "quasi-doublon d'une image d'entraînement"
    assert reasons["m.jpg"] == "étiquette non prévue dans le mapping"
    assert reasons["Healthy0.jpg"] == ""  # l'original d'entraînement est conservé

    kept = df[df["excluded_reason"] == ""]
    assert set(kept.loc[kept["source"] == "test_src", "split"]) == {"test_test_src"}
    assert set(kept.loc[kept["source"] == "train_src", "split"]) <= {"train", "val", "test"}
    assert_no_group_leakage(kept["group"].tolist(), kept["split"].tolist())
    # Découpage par date : toutes les images d'un même jour dans le même ensemble.
    per_day = kept[kept["source"] == "train_src"].groupby("exif_date")["split"].nunique()
    assert (per_day == 1).all() and len(per_day) == 3

    out = tmp_path / "processed"
    manifest = materialize(df, interim, out)
    assert (out / "manifest.csv").exists() and (out / "summary.json").exists()
    linked = list((out / "test_test_src").rglob("*.jpg"))
    assert len(linked) == 10
    assert linked[0].stat().st_nlink >= 2  # lien physique, pas de copie
    files = manifest.loc[manifest["excluded_reason"] == "", "file"]
    assert all((out / f).is_file() for f in files)
    assert (manifest.loc[manifest["excluded_reason"] != "", "file"] == "").all()


def test_materialize_never_overwrites_same_name(tmp_path: Path) -> None:
    root = tmp_path / "interim"
    _save(_image(1), root / "src" / "a" / "Rust1.png")
    _save(_image(2), root / "src" / "b" / "Rust1.png")  # même nom, autre image
    cfg = ClassificationDataConfig(
        classes=["rust"],
        sources={
            "src": SourceSpec(label_from="filename_prefix", mapping={"Rust": "rust"}, role="test")
        },
    )
    df = assign_splits(add_fingerprints(scan_sources(cfg, root), root, workers=1), cfg)
    manifest = materialize(df, root, tmp_path / "out")
    files = manifest["file"].tolist()
    assert len(set(files)) == 2
    contents = {(tmp_path / "out" / f).read_bytes() for f in files}
    assert len(contents) == 2  # aucune image écrasée par l'autre


def test_raw_label_from_filename_prefix() -> None:
    spec = SourceSpec(label_from="filename_prefix", mapping={}, role="train")
    assert raw_label(Path("x/BrownRust1018.png"), spec) == "BrownRust"
    assert raw_label(Path("x/Septoria_12.jpg"), spec) == "Septoria"


def test_config_rejects_unknown_classes() -> None:
    with pytest.raises(ValueError, match="classes inconnues"):
        ClassificationDataConfig(
            classes=["healthy"], sources={"s": SourceSpec(mapping={"a": "rust"}, role="train")}
        )


def test_sequence_gap_groups_consecutive_files(tmp_path: Path) -> None:
    root = tmp_path / "interim"
    for n, seed in [(1, 1), (2, 2), (3, 3), (10, 4), (40, 5)]:
        _save(_image(seed), root / "seq" / f"Rust{n}.png")
    cfg = ClassificationDataConfig(
        classes=["rust"],
        sources={
            "seq": SourceSpec(
                label_from="filename_prefix", mapping={"Rust": "rust"}, role="train", sequence_gap=2
            )
        },
    )
    df = assign_splits(add_fingerprints(scan_sources(cfg, root), root, workers=1), cfg)
    group = dict(zip(df["path"].str.split("/").str[-1], df["group"], strict=True))
    assert group["Rust1.png"] == group["Rust2.png"] == group["Rust3.png"]
    assert len({group["Rust1.png"], group["Rust10.png"], group["Rust40.png"]}) == 3
