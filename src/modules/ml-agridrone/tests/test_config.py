from __future__ import annotations

from pathlib import Path

import pytest

from agridrone.core.config import (
    ConfigError,
    ExperimentConfig,
    apply_overrides,
    config_hash,
    deep_merge,
    load_config,
    load_experiment,
    parse_override,
    parse_yaml,
    validate_config,
)


def test_deep_merge_merges_sections_and_replaces_lists() -> None:
    base = {"a": {"x": 1, "y": 2}, "l": [1, 2], "s": "keep"}
    override = {"a": {"y": 3, "z": 4}, "l": [9]}
    merged = deep_merge(base, override)
    assert merged == {"a": {"x": 1, "y": 3, "z": 4}, "l": [9], "s": "keep"}
    assert base == {"a": {"x": 1, "y": 2}, "l": [1, 2], "s": "keep"}  # entrées intactes


def test_inheritance_chain_and_multiple_bases(write_yaml) -> None:  # type: ignore[no-untyped-def]
    write_yaml("base.yaml", "seed: 1\npaths: {raw: r, runs: runs}\nname: base\n")
    write_yaml("extra.yaml", "num_workers: 0\nname: extra\n")
    write_yaml("task/mid.yaml", "_base_: [../base.yaml, ../extra.yaml]\nseed: 2\n")
    leaf = write_yaml("task/sub/leaf.yaml", "_base_: ../mid.yaml\npaths: {raw: leaf_raw}\n")

    cfg = load_config(leaf)
    assert cfg["seed"] == 2  # mid > base
    assert cfg["name"] == "extra"  # bases fusionnées dans l'ordre
    assert cfg["num_workers"] == 0
    assert cfg["paths"] == {"raw": "leaf_raw", "runs": "runs"}  # fusion récursive
    assert "_base_" not in cfg


def test_inheritance_cycle_is_detected(write_yaml) -> None:  # type: ignore[no-untyped-def]
    write_yaml("a.yaml", "_base_: b.yaml\n")
    b = write_yaml("b.yaml", "_base_: a.yaml\n")
    with pytest.raises(ConfigError, match="cyclique"):
        load_config(b)


def test_missing_file_and_non_mapping_root(write_yaml, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "absent.yaml")
    with pytest.raises(ConfigError, match="dictionnaire"):
        load_config(write_yaml("list.yaml", "- 1\n- 2\n"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1e-3", 1e-3),
        ("2E5", 2e5),
        ("1.5e+2", 150.0),
        ("0.1", 0.1),
        ("42", 42),
        ("true", True),
        ("null", None),
        ("[1, 2]", [1, 2]),
        ("'1e-3'", "1e-3"),
        ("yolo11n.pt", "yolo11n.pt"),
    ],
)
def test_yaml_scalar_parsing(text: str, expected: object) -> None:
    assert parse_yaml(text) == expected


def test_parse_override() -> None:
    assert parse_override("train.lr=1e-4") == (["train", "lr"], 1e-4)
    assert parse_override("name=a=b") == (["name"], "a=b")
    for bad in ("seed", "=3", "a..b=1"):
        with pytest.raises(ConfigError):
            parse_override(bad)


def test_apply_overrides_creates_keys_without_mutating_input() -> None:
    cfg = {"paths": {"raw": "r"}, "seed": 1}
    out = apply_overrides(cfg, ["paths.raw=x", "seed=3", "new.section.key=on"])
    assert out == {"paths": {"raw": "x"}, "seed": 3, "new": {"section": {"key": True}}}
    assert cfg == {"paths": {"raw": "r"}, "seed": 1}
    with pytest.raises(ConfigError, match="n'est pas une section"):
        apply_overrides(cfg, ["seed.sub=1"])


def test_validation_rejects_unknown_keys_tasks_and_devices() -> None:
    with pytest.raises(ConfigError, match="seeed"):
        validate_config({"seeed": 1})
    with pytest.raises(ConfigError, match="Tâche inconnue"):
        validate_config({"task": "teleportation"})
    with pytest.raises(ConfigError):
        validate_config({"device": "gpu"})
    assert validate_config({"device": "cuda:1"}).device == "cuda:1"


def test_config_hash_ignores_key_order_but_not_values() -> None:
    a = {"x": 1, "y": {"b": 2, "a": 1}}
    b = {"y": {"a": 1, "b": 2}, "x": 1}
    assert config_hash(a) == config_hash(b)
    assert config_hash(a) != config_hash({**a, "x": 2})


def test_repository_base_config_is_valid(repo_root: Path) -> None:
    cfg = load_experiment(repo_root / "configs" / "base.yaml", ["seed=7"])
    assert isinstance(cfg, ExperimentConfig)
    assert cfg.seed == 7
    assert cfg.task == "base"
