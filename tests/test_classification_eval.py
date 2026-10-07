from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from agridrone.eval.classification import (
    UNCERTAIN,
    DecisionRule,
    calibrate_decision_rule,
    confusion_matrix,
    expected_calibration_error,
    plot_confusion,
    plot_risk_coverage,
    risk_coverage,
    summarize_predictions,
)

CLASSES = ["healthy", "rust", "septoria"]


def test_confusion_matrix_has_uncertain_column() -> None:
    cm = confusion_matrix(np.array([0, 0, 1, 1, 2]), np.array([0, 1, 1, UNCERTAIN, 0]), 3)
    assert cm.tolist() == [[1, 1, 0, 0], [0, 1, 0, 1], [1, 0, 0, 0]]
    with pytest.raises(ValueError):
        confusion_matrix(np.array([3]), np.array([0]), 3)
    with pytest.raises(ValueError):
        confusion_matrix(np.array([0]), np.array([-2]), 3)


def test_summary_with_abstention_and_binary_view() -> None:
    s = summarize_predictions(
        np.array([0, 0, 1, 1, 2]), np.array([0, 1, 1, UNCERTAIN, 0]), CLASSES, healthy_index=0
    )
    assert s["coverage"] == pytest.approx(0.8)
    assert s["accuracy"] == pytest.approx(0.4)  # « incertain » compte comme erreur
    assert s["selective_accuracy"] == pytest.approx(0.5)
    healthy, rust, septoria = (s["per_class"][c] for c in CLASSES)
    assert healthy["precision"] == pytest.approx(0.5) and healthy["recall"] == pytest.approx(0.5)
    assert rust["recall"] == pytest.approx(0.5) and rust["uncertain"] == 1
    assert septoria["precision"] is None and septoria["f1"] == 0.0  # jamais prédite
    assert s["macro_f1"] == pytest.approx((0.5 + 0.5 + 0.0) / 3)
    b = s["binary"]
    assert (b["n_diseased"], b["n_healthy"]) == (3, 2)
    assert b["disease_detected"] == pytest.approx(1 / 3)
    assert b["disease_uncertain"] == pytest.approx(1 / 3)
    assert b["disease_missed"] == pytest.approx(1 / 3)  # septoriose déclarée saine
    assert b["healthy_correct"] == pytest.approx(0.5)
    assert b["healthy_false_alarm"] == pytest.approx(0.5)


def test_absent_classes_are_left_out_of_macro_f1() -> None:
    # Test inter-sources sans septoriose : une prédiction « septoriose » reste une erreur.
    s = summarize_predictions(np.array([0, 0, 1, 1]), np.array([0, 0, 1, 2]), CLASSES, 0)
    septoria = s["per_class"]["septoria"]
    assert septoria["support"] == 0 and septoria["recall"] is None and septoria["f1"] is None
    assert septoria["precision"] == 0.0
    rust_f1 = 2 * 1.0 * 0.5 / 1.5
    assert s["macro_f1"] == pytest.approx((1.0 + rust_f1) / 2)


def test_decision_rule_requires_more_confidence_for_healthy() -> None:
    rule = DecisionRule(tau=0.5, tau_healthy=0.8, healthy_index=0)
    probs = np.array(
        [
            [0.90, 0.05, 0.05],  # sain sûr -> sain
            [0.70, 0.20, 0.10],  # sain peu sûr -> incertain
            [0.20, 0.70, 0.10],  # rouille -> rouille
            [0.30, 0.40, 0.30],  # trop peu sûr -> incertain
        ]
    )
    assert rule.apply(probs).tolist() == [0, UNCERTAIN, 1, UNCERTAIN]
    assert DecisionRule.from_dict(rule.to_dict()) == rule


def test_calibration_reaches_coverage_and_caps_missed_diseases() -> None:
    rng = np.random.default_rng(0)
    n = 200
    y = rng.integers(0, 3, n)
    logits = rng.normal(size=(n, 3)) + 2.5 * np.eye(3)[y]
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)

    rule = calibrate_decision_rule(probs, y, 0, target_coverage=0.9, max_missed_rate=0.02)
    assert (probs.max(axis=1) >= rule.tau).mean() >= 0.9
    decided = rule.apply(probs)
    diseased = y != 0
    assert (decided[diseased] == 0).mean() <= 0.02
    assert rule.tau_healthy >= rule.tau

    # Sans contrainte sur les ratés, « sain » n'exige rien de plus.
    loose = calibrate_decision_rule(probs, y, 0, target_coverage=1.0, max_missed_rate=1.0)
    assert loose.tau == 0.0 and loose.tau_healthy == loose.tau
    with pytest.raises(ValueError):
        calibrate_decision_rule(probs, y, 0, target_coverage=0.0, max_missed_rate=0.1)


def test_calibration_removes_least_confident_misses_first() -> None:
    # 10 images malades dont 3 déclarées saines avec p(sain) = 0.6, 0.7, 0.9.
    p_healthy = [0.6, 0.7, 0.9] + [0.1] * 7
    probs = np.array([[p, 1 - p, 0.0] for p in p_healthy] + [[0.95, 0.05, 0.0]])
    y = np.array([1] * 10 + [0])
    rule = calibrate_decision_rule(probs, y, 0, target_coverage=1.0, max_missed_rate=0.1)
    assert 0.7 < rule.tau_healthy <= 0.9
    decided = rule.apply(probs)
    assert decided[:3].tolist() == [UNCERTAIN, UNCERTAIN, 0]  # un seul raté toléré (10 %)
    assert decided[-1] == 0  # l'image saine très sûre reste « saine »


def test_expected_calibration_error_and_risk_coverage() -> None:
    y = np.array([0, 1, 0, 1])
    perfect = np.eye(2)[y]
    assert expected_calibration_error(perfect, y) == pytest.approx(0.0)
    overconfident = np.array([[0.9, 0.1]] * 4)  # 90 % de confiance, 50 % de réussite
    assert expected_calibration_error(overconfident, y) == pytest.approx(0.4)

    probs = np.array([[0.9, 0.1], [0.4, 0.6], [0.55, 0.45], [0.8, 0.2]])
    coverage, accuracy = risk_coverage(probs, np.array([0, 1, 1, 0]))
    assert coverage.tolist() == [0.25, 0.5, 0.75, 1.0]
    assert accuracy[-1] == pytest.approx(0.75) and accuracy[0] == 1.0


def test_plot_confusion_writes_png(tmp_path: Path) -> None:
    cm = confusion_matrix(np.array([0, 1, 1]), np.array([0, UNCERTAIN, 1]), 3)
    for with_uncertain in (True, False):
        path = plot_confusion(
            cm,
            CLASSES,
            tmp_path / f"cm_{with_uncertain}.png",
            title="t",
            with_uncertain=with_uncertain,
        )
        assert path.stat().st_size > 1000


def test_plot_risk_coverage_writes_png(tmp_path: Path) -> None:
    rng = np.random.default_rng(1)
    curves = {}
    for name in ("a", "b"):
        probs = rng.dirichlet(np.ones(3), size=50)
        curves[name] = risk_coverage(probs, rng.integers(0, 3, 50))
    path = plot_risk_coverage(
        curves, tmp_path / "rc.png", title="t", operating_points={"a": (0.8, 0.5)}
    )
    assert path.stat().st_size > 1000
    with pytest.raises(ValueError):
        plot_risk_coverage({str(i): curves["a"] for i in range(9)}, tmp_path / "x.png", title="t")
