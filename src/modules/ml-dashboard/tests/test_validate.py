"""Tests du validateur : un run valide passe, chaque règle cassée est détectée."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from ml_dashboard import standard as S
from ml_dashboard.cli import main
from ml_dashboard.schema_lite import load_schema, validate_instance
from ml_dashboard.validate import find_runs, validate_run

MakeRun = Callable[..., Path]


def _messages(report) -> str:
    return "\n".join(f"{i.level} {i.file} {i.message}" for i in report.issues)


def _edit_json(path: Path, **changes) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    path.write_text(json.dumps(data), encoding="utf-8")


def _assert_error(report, needle: str) -> None:
    assert not report.ok, _messages(report)
    assert any(needle in i.message for i in report.errors), _messages(report)


# --------------------------------------------------------------------------- #
# Runs valides
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "kwargs",
    [
        {"task": "classification"},
        {"task": "classification", "classes": ["sain", "mildiou", "oidium", "carence eau"]},
        {"task": "classification", "label_mode": "multi", "classes": ["mildiou", "carence_eau", "insectes"]},
        {"task": "detection"},
        {"task": "segmentation"},
        {"task": "classification", "status": "running"},
    ],
)
def test_valid_runs(make_run: MakeRun, kwargs) -> None:
    report = validate_run(make_run(**kwargs))
    assert report.ok, _messages(report)
    assert report.schema_version == 1
    assert not report.warnings, _messages(report)


def test_schemas_are_valid_json() -> None:
    for name in ("meta", "classes", "manifest", "detection_metrics"):
        schema = load_schema(name)
        assert schema["properties"]["schema_version"] == {"const": 1}


# --------------------------------------------------------------------------- #
# meta.json
# --------------------------------------------------------------------------- #
def test_missing_meta(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.META_FILE).unlink()
    _assert_error(validate_run(run), "fichier manquant")


def test_future_schema_version_is_refused(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.META_FILE, schema_version=99)
    _assert_error(validate_run(run), "mets à jour ml_dashboard")


def test_run_id_must_match_folder(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.META_FILE, run_id="20261029_180500_autre")
    _assert_error(validate_run(run), "différent du nom du dossier")


def test_invalid_task(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.META_FILE, task="regression")
    _assert_error(validate_run(run), "hors de")


def test_unknown_meta_key(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.META_FILE, foo=1)
    _assert_error(validate_run(run), "clé non autorisée 'foo'")


def test_bool_is_not_an_integer(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.META_FILE, seed=True)
    _assert_error(validate_run(run), "seed")


# --------------------------------------------------------------------------- #
# config.yaml / classes.json
# --------------------------------------------------------------------------- #
def test_config_must_be_mapping(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.CONFIG_FILE).write_text("- a\n- b\n", encoding="utf-8")
    _assert_error(validate_run(run), "dictionnaire")


def test_positive_class_must_exist(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.CLASSES_FILE, positive_class="absente")
    _assert_error(validate_run(run), "absente de classes")


def test_pipe_forbidden_in_class_names(make_run: MakeRun) -> None:
    run = make_run()
    _edit_json(run / S.CLASSES_FILE, classes=["a|b", "c"], positive_class=None)
    _assert_error(validate_run(run), "motif")


def test_multilabel_rejects_positive_class(make_run: MakeRun) -> None:
    run = make_run(label_mode="multi", classes=["mildiou", "insectes"])
    _edit_json(run / S.CLASSES_FILE, positive_class="mildiou")
    _assert_error(validate_run(run), "multi-label")


# --------------------------------------------------------------------------- #
# epochs.csv
# --------------------------------------------------------------------------- #
def test_bad_epoch_column_name(make_run: MakeRun) -> None:
    run = make_run()
    df = pd.read_csv(run / S.EPOCHS_FILE)
    df["Accuracy"] = 0.5
    df.to_csv(run / S.EPOCHS_FILE, index=False)
    _assert_error(validate_run(run), "non conformes")


def test_epochs_must_increase(make_run: MakeRun) -> None:
    run = make_run()
    df = pd.read_csv(run / S.EPOCHS_FILE)
    df["epoch"] = [0, 2, 1]
    df.to_csv(run / S.EPOCHS_FILE, index=False)
    _assert_error(validate_run(run), "strictement croissante")


def test_epochs_missing_required_column(make_run: MakeRun) -> None:
    run = make_run()
    pd.read_csv(run / S.EPOCHS_FILE).drop(columns="lr").to_csv(run / S.EPOCHS_FILE, index=False)
    _assert_error(validate_run(run), "obligatoires manquantes")


def test_completed_run_needs_epochs(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.EPOCHS_FILE).write_text("epoch,lr,train_loss,val_loss\n", encoding="utf-8")
    _assert_error(validate_run(run), "aucune époque")


def test_split_metric_column() -> None:
    assert S.split_metric_column("val_recall__carence eau") == ("val", "recall", "carence eau")
    with pytest.raises(ValueError):
        S.split_metric_column("valacc")


# --------------------------------------------------------------------------- #
# predictions/
# --------------------------------------------------------------------------- #
def test_probas_must_sum_to_one(make_run: MakeRun) -> None:
    run = make_run()
    path = run / S.PREDICTIONS_DIR / "val.csv"
    df = pd.read_csv(path)
    df.loc[0, "proba_sain"] = 0.99
    df.loc[0, "proba_malade"] = 0.99
    df.to_csv(path, index=False)
    _assert_error(validate_run(run), "ne somment pas à 1")


def test_unknown_class_in_predictions(make_run: MakeRun) -> None:
    run = make_run()
    path = run / S.PREDICTIONS_DIR / "val.csv"
    df = pd.read_csv(path)
    df.loc[0, "y_true"] = "inconnue"
    df.to_csv(path, index=False)
    _assert_error(validate_run(run), "classes inconnues")


def test_missing_proba_column(make_run: MakeRun) -> None:
    run = make_run()
    path = run / S.PREDICTIONS_DIR / "val.csv"
    pd.read_csv(path).drop(columns="proba_sain").to_csv(path, index=False)
    _assert_error(validate_run(run), "probabilité manquantes")


def test_duplicate_ids(make_run: MakeRun) -> None:
    run = make_run()
    path = run / S.PREDICTIONS_DIR / "val.csv"
    df = pd.read_csv(path)
    df.loc[1, "id"] = df.loc[0, "id"]
    df.to_csv(path, index=False)
    _assert_error(validate_run(run), "en double")


def test_test_split_only_when_completed(make_run: MakeRun) -> None:
    run = make_run(status="running")
    src = run / S.PREDICTIONS_DIR / "val.csv"
    (run / S.PREDICTIONS_DIR / "test.csv").write_bytes(src.read_bytes())
    _assert_error(validate_run(run), "fin de run")


def test_completed_classification_needs_val(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.PREDICTIONS_DIR / "val.csv").unlink()
    _assert_error(validate_run(run), "manquant pour un run terminé")


def test_y_pred_threshold_mismatch_is_warning(make_run: MakeRun) -> None:
    run = make_run()
    path = run / S.PREDICTIONS_DIR / "val.csv"
    df = pd.read_csv(path)
    df["y_pred"] = "malade"  # comme si un seuil réglé avait été appliqué
    df.to_csv(path, index=False)
    report = validate_run(run)
    assert report.ok
    assert any("proba maximale" in w.message for w in report.warnings)


def test_multilabel_unknown_class(make_run: MakeRun) -> None:
    run = make_run(label_mode="multi", classes=["mildiou", "insectes"])
    path = run / S.PREDICTIONS_DIR / "val.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.loc[0, "y_true"] = "mildiou|rouille"
    df.to_csv(path, index=False)
    _assert_error(validate_run(run), "classes inconnues")


def test_multilabel_empty_label_is_allowed(make_run: MakeRun) -> None:
    run = make_run(label_mode="multi", classes=["mildiou", "insectes"])
    path = run / S.PREDICTIONS_DIR / "val.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.loc[0, "y_true"] = ""  # image saine : aucune classe
    df.to_csv(path, index=False)
    assert validate_run(run).ok


# --------------------------------------------------------------------------- #
# detection/, artifacts/, extra_results/, model/
# --------------------------------------------------------------------------- #
def test_detection_needs_metrics(make_run: MakeRun) -> None:
    run = make_run(task="detection")
    (run / S.DETECTION_DIR / S.DETECTION_METRICS_FILE).unlink()
    _assert_error(validate_run(run), "détection terminé")


def test_detection_metric_out_of_range(make_run: MakeRun) -> None:
    run = make_run(task="detection")
    path = run / S.DETECTION_DIR / S.DETECTION_METRICS_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    data["box"]["map50"] = 55.0  # pourcentage au lieu de fraction
    path.write_text(json.dumps(data), encoding="utf-8")
    _assert_error(validate_run(run), "maximum")


def test_artifact_manifest_missing_file(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.ARTIFACTS_DIR / "gradcam.png").unlink()
    (run / S.ARTIFACTS_DIR / "autre.png").write_bytes(b"x")
    report = validate_run(run)
    _assert_error(report, "absent")
    assert any("non décrits" in w.message for w in report.warnings)


def test_artifact_manifest_required(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.ARTIFACTS_DIR / S.MANIFEST_FILE).unlink()
    _assert_error(validate_run(run), "fichier manquant")


def test_manifest_path_traversal(make_run: MakeRun) -> None:
    run = make_run()
    path = run / S.ARTIFACTS_DIR / S.MANIFEST_FILE
    path.write_text(json.dumps({"schema_version": 1, "items": [
        {"file": "gradcam.png", "title": "ok"}, {"file": "../meta.json", "title": "x"}]}), encoding="utf-8")
    _assert_error(validate_run(run), "sort du dossier")


def test_missing_model_is_warning(make_run: MakeRun) -> None:
    run = make_run()
    (run / S.MODEL_DIR / "best.pt").unlink()
    report = validate_run(run)
    assert report.ok
    assert any("checkpoint" in w.message for w in report.warnings)


def test_unexpected_top_level_entry_is_warning(make_run: MakeRun) -> None:
    run = make_run()
    (run / "notes.txt").write_text("x", encoding="utf-8")
    report = validate_run(run)
    assert report.ok and report.warnings


# --------------------------------------------------------------------------- #
# Découverte et CLI
# --------------------------------------------------------------------------- #
def test_find_runs_from_any_level(make_run: MakeRun) -> None:
    run = make_run()
    for root in (run, run.parent, run.parent.parent):
        assert find_runs(root) == [run.resolve()]


def test_cli_exit_codes(make_run: MakeRun, tmp_path: Path, capsys) -> None:
    run = make_run()
    assert main(["validate", str(run.parent.parent)]) == 0
    assert "1/1 run(s) valide(s)" in capsys.readouterr().out

    (run / "notes.txt").write_text("x", encoding="utf-8")
    assert main(["validate", "--strict", str(run)]) == 1

    (run / S.CONFIG_FILE).unlink()
    assert main(["validate", "--json", str(run)]) == 1
    empty = tmp_path / "vide"
    empty.mkdir()
    assert main(["validate", str(empty)]) == 2


def test_cli_json_output(make_run: MakeRun, capsys) -> None:
    run = make_run()
    (run / S.CONFIG_FILE).unlink()
    assert main(["validate", "--json", str(run)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["ok"] is False
    assert payload[0]["issues"][0]["file"] == S.CONFIG_FILE


def test_schema_lite_ref_and_types() -> None:
    schema = {"type": "object", "properties": {"x": {"$ref": "#/$defs/n"}}, "$defs": {"n": {"type": "integer"}}}
    assert validate_instance({"x": 1}, schema) == []
    assert validate_instance({"x": "a"}, schema)
