"""Entraînement et évaluation du classifieur de maladies du blé (chantier 4).

Transfer learning timm (EfficientNet-B0, ConvNeXt-Tiny) sur le jeu préparé par
``agridrone data prepare-classification`` :

1. entraînement sur l'ensemble ``train`` (John Innes), sélection du modèle sur ``val``
   (macro-F1), arrêt anticipé ;
2. calibration de la règle de décision sur ``val`` (sortie « incertain », priorité au
   rappel des maladies, voir :mod:`agridrone.eval.classification`) ;
3. évaluation sur le test intra-source et les tests inter-sources (Éthiopie,
   YellowRust_22-23), jamais vus à l'entraînement ni à la calibration.

Sorties dans le dossier du run : ``best.pt`` (checkpoint avec sa règle de décision),
``history.csv`` et ``history.png``, puis ``eval/metrics.json`` et, par ensemble,
``eval/<ensemble>/`` (prédictions CSV, matrices de confusion).
"""

from __future__ import annotations

import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
import torch
from pydantic import Field, model_validator
from torch import nn
from torch.optim.lr_scheduler import LambdaLR
from torch.utils.data import DataLoader

from agridrone.core.config import ExperimentConfig, StrictModel, register_task_schema
from agridrone.core.device import Precision, autocast_context, resolve_device
from agridrone.core.paths import project_root, resolve_path
from agridrone.core.run import init_run, tracking_run
from agridrone.data.augment import rgb_eval_transform, rgb_train_transform
from agridrone.data.datasets import ClassificationDataset, classification_split
from agridrone.eval.classification import (
    calibrate_decision_rule,
    expected_calibration_error,
    plot_confusion,
    plot_risk_coverage,
    risk_coverage,
    summarize_predictions,
)
from agridrone.models.classifier import ClassifierCheckpoint, build_classifier, normalization
from agridrone.training.common import (
    balanced_class_weights,
    make_loader,
    plot_history,
    warmup_cosine,
)

# ---------------------------------------------------------------------------
# Schéma de config
# ---------------------------------------------------------------------------


class ClassificationData(StrictModel):
    #: Dossier du jeu préparé (contient ``manifest.csv``), relatif à la racine du projet.
    dir: Path = Path("data/processed/classification")
    #: Ordre = ordre des sorties du modèle.
    classes: list[str] = Field(min_length=2)
    healthy_class: str = "healthy"
    #: Noms affichés dans les figures (par défaut : identifiants des classes).
    display_names: dict[str, str] = Field(default_factory=dict)
    train_split: str = "train"
    #: Sélection du modèle et calibration des seuils.
    val_split: str = "val"
    test_splits: list[str] = Field(default_factory=lambda: ["test"])
    #: Noms affichés des ensembles dans les figures (par défaut : identifiants).
    split_names: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_classes(self) -> ClassificationData:
        if len(set(self.classes)) != len(self.classes):
            raise ValueError(f"classes en double : {self.classes}")
        if self.healthy_class not in self.classes:
            raise ValueError(f"healthy_class {self.healthy_class!r} absente de {self.classes}")
        unknown = sorted(set(self.display_names) - set(self.classes))
        if unknown:
            raise ValueError(f"display_names : classes inconnues {unknown}")
        splits = {self.train_split, self.val_split, *self.test_splits}
        unknown = sorted(set(self.split_names) - splits)
        if unknown:
            raise ValueError(f"split_names : ensembles inconnus {unknown}")
        return self

    def names(self) -> list[str]:
        return [self.display_names.get(c, c) for c in self.classes]

    def split_name(self, split: str) -> str:
        return self.split_names.get(split, split)


class ClassifierModel(StrictModel):
    #: Architecture timm avec l'étiquette des poids, ex. ``efficientnet_b0.ra_in1k``.
    arch: str
    pretrained: bool = True
    input_size: int = Field(default=224, ge=32)
    drop_rate: float = Field(default=0.0, ge=0.0, lt=1.0)
    drop_path_rate: float = Field(default=0.0, ge=0.0, lt=1.0)


class ClassificationTrain(StrictModel):
    epochs: int = Field(default=25, ge=1)
    batch_size: int = Field(default=32, ge=2)
    lr: float = Field(default=5e-4, gt=0.0)
    weight_decay: float = Field(default=0.01, ge=0.0)
    warmup_epochs: float = Field(default=1.0, ge=0.0)
    #: Taux final = lr × min_lr_ratio (décroissance en cosinus).
    min_lr_ratio: float = Field(default=0.01, ge=0.0, le=1.0)
    class_weights: Literal["balanced", "none"] = "balanced"
    label_smoothing: float = Field(default=0.0, ge=0.0, lt=1.0)
    #: Arrêt après ``patience`` époques sans progrès du macro-F1 de validation.
    patience: int | None = Field(default=8, ge=1)
    precision: Precision = "fp32"


class ClassificationEval(StrictModel):
    batch_size: int = Field(default=64, ge=1)
    precision: Precision = "fp32"
    #: Part des images de validation qui reçoivent une décision (le reste : « incertain »).
    target_coverage: float = Field(default=0.9, gt=0.0, le=1.0)
    #: Part maximale d'images malades déclarées saines, sur la validation.
    max_missed_rate: float = Field(default=0.02, ge=0.0, le=1.0)


@register_task_schema("classification")
class ClassificationExperiment(ExperimentConfig):
    task: str = "classification"
    data: ClassificationData
    model: ClassifierModel
    train: ClassificationTrain = Field(default_factory=ClassificationTrain)
    eval: ClassificationEval = Field(default_factory=ClassificationEval)


# ---------------------------------------------------------------------------
# Boucles
# ---------------------------------------------------------------------------


def read_manifest(data_dir: Path) -> pd.DataFrame:
    path = data_dir / "manifest.csv"
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} introuvable : lancer `agridrone data prepare-classification`"
        )
    manifest = pd.read_csv(path, keep_default_na=False, dtype={"file": str})
    if "file" not in manifest.columns:
        raise ValueError(f"{path} : colonne 'file' absente, relancer la préparation des données")
    return manifest


@torch.inference_mode()
def predict(
    model: nn.Module, loader: DataLoader[Any], device: torch.device, precision: Precision
) -> tuple[np.ndarray, np.ndarray]:
    """Probabilités softmax (N, K) en float64 et étiquettes (N,)."""
    model.eval()
    probs: list[np.ndarray] = []
    labels: list[np.ndarray] = []
    for x, y in loader:
        with autocast_context(device, precision):
            logits = model(x.to(device, non_blocking=True))
        probs.append(torch.softmax(logits.float(), dim=1).cpu().numpy())
        labels.append(y.numpy())
    return np.concatenate(probs).astype(np.float64), np.concatenate(labels)


def _nll(probs: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.clip(probs[np.arange(len(y)), y], 1e-12, None)).mean())


def _train_one_epoch(
    model: nn.Module,
    loader: DataLoader[Any],
    criterion: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: LambdaLR,
    device: torch.device,
    precision: Precision,
) -> float:
    model.train()
    total, count = 0.0, 0
    for x, y in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        optimizer.zero_grad(set_to_none=True)
        with autocast_context(device, precision):
            logits = model(x)
        loss = criterion(logits.float(), y)  # perte en float32, hors autocast
        loss.backward()
        optimizer.step()
        scheduler.step()
        total += loss.item() * len(y)
        count += len(y)
    return total / count


def _split_loader(
    cfg: ClassificationExperiment,
    manifest: pd.DataFrame,
    data_dir: Path,
    split: str,
    ckpt: ClassifierCheckpoint,
    device: torch.device,
) -> tuple[list[Path], DataLoader[Any]]:
    files, labels = classification_split(manifest, data_dir, split, ckpt.classes)
    dataset = ClassificationDataset(
        files,
        labels,
        rgb_eval_transform(ckpt.input_size),
        mean=ckpt.mean,
        std=ckpt.std,
        decode_size=ckpt.input_size,
    )
    loader = make_loader(
        dataset,
        batch_size=cfg.eval.batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        seed=cfg.seed,
        pin_memory=device.type == "cuda",
    )
    return files, loader


def run_evaluation(
    cfg: ClassificationExperiment,
    ckpt: ClassifierCheckpoint,
    out_dir: Path,
    device: torch.device,
    *,
    root: Path,
) -> dict[str, Any]:
    """Calibre la règle de décision sur ``val`` puis évalue val et les ensembles de test.

    Écrit ``out_dir/metrics.json``, ``out_dir/risk_coverage.png`` (ensembles de test)
    et, par ensemble, ``out_dir/<ensemble>/`` : ``predictions.csv``,
    ``confusion_argmax.png``, ``confusion_decision.png``.
    """
    if ckpt.classes != cfg.data.classes:
        raise ValueError(f"classes du checkpoint {ckpt.classes} ≠ config {cfg.data.classes}")
    data_dir = resolve_path(cfg.data.dir, root)
    manifest = read_manifest(data_dir)
    model = ckpt.build_model().to(device)
    classes, names = cfg.data.classes, cfg.data.names()
    healthy = classes.index(cfg.data.healthy_class)
    title = cfg.model.arch

    outputs: dict[str, tuple[list[Path], np.ndarray, np.ndarray, float]] = {}
    for split in [cfg.data.val_split, *cfg.data.test_splits]:
        files, loader = _split_loader(cfg, manifest, data_dir, split, ckpt, device)
        start = time.perf_counter()
        probs, y = predict(model, loader, device, cfg.eval.precision)
        outputs[split] = (files, probs, y, len(y) / (time.perf_counter() - start))

    _, val_probs, val_y, _ = outputs[cfg.data.val_split]
    rule = calibrate_decision_rule(
        val_probs,
        val_y,
        healthy,
        target_coverage=cfg.eval.target_coverage,
        max_missed_rate=cfg.eval.max_missed_rate,
    )
    results: dict[str, Any] = {
        "checkpoint": ckpt.metadata,
        "decision_rule": rule.to_dict(),
        "calibrated_on": cfg.data.val_split,
        "splits": {},
    }
    for split, (files, probs, y, speed) in outputs.items():
        argmax, decided = probs.argmax(axis=1), rule.apply(probs)
        summary_argmax = summarize_predictions(y, argmax, classes, healthy)
        summary_decision = summarize_predictions(y, decided, classes, healthy)
        results["splits"][split] = {
            "n": len(y),
            "argmax": summary_argmax,
            "decision": summary_decision,
            "ece": expected_calibration_error(probs, y),
            "images_per_second": speed,
        }
        split_dir = out_dir / split
        table = pd.DataFrame(
            {
                "file": [f.relative_to(data_dir).as_posix() for f in files],
                "label": [classes[i] for i in y],
                "argmax": [classes[i] for i in argmax],
                "decision": [classes[i] if i >= 0 else "uncertain" for i in decided],
                "confidence": probs.max(axis=1),
                **{f"p_{c}": probs[:, i] for i, c in enumerate(classes)},
            }
        )
        split_dir.mkdir(parents=True, exist_ok=True)
        table.to_csv(split_dir / "predictions.csv", index=False, float_format="%.6f")
        cm_argmax = np.asarray(summary_argmax["confusion"])
        cm_decision = np.asarray(summary_decision["confusion"])
        shown = cfg.data.split_name(split)
        plot_confusion(
            cm_argmax,
            names,
            split_dir / "confusion_argmax.png",
            title=f"{title} · {shown}\nsans abstention",
            with_uncertain=False,
        )
        coverage = summary_decision["coverage"]
        plot_confusion(
            cm_decision,
            names,
            split_dir / "confusion_decision.png",
            title=f"{title} · {shown}\nrègle de décision (couverture {coverage:.0%})",
        )
    tests = [s for s in outputs if s != cfg.data.val_split]
    plot_risk_coverage(
        {cfg.data.split_name(s): risk_coverage(outputs[s][1], outputs[s][2]) for s in tests},
        out_dir / "risk_coverage.png",
        title=f"{title} : exactitude selon la couverture (tests)",
        operating_points={
            cfg.data.split_name(s): (
                results["splits"][s]["decision"]["coverage"],
                results["splits"][s]["decision"]["selective_accuracy"] or 0.0,
            )
            for s in tests
        },
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return results


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f} %"


def format_results(results: dict[str, Any]) -> str:
    """Tableau texte : sans abstention, puis avec la règle de décision."""
    rule = results["decision_rule"]
    lines = [
        f"Règle de décision (calibrée sur {results['calibrated_on']}) : "
        f"tau = {rule['tau']:.3f}, tau_sain = {rule['tau_healthy']:.3f}",
        f"{'ensemble':30s} {'n':>6s} │ {'exact.':>7s} {'F1 macro':>8s} {'ratés':>7s} │ "
        f"{'couv.':>7s} {'exact.sél.':>10s} {'ratés':>7s} │ {'ECE':>5s}",
    ]
    for split, r in results["splits"].items():
        a, d = r["argmax"], r["decision"]
        lines.append(
            f"{split:30s} {r['n']:6d} │ {_pct(a['accuracy']):>7s} {a['macro_f1']:8.3f} "
            f"{_pct(a['binary']['disease_missed']):>7s} │ {_pct(d['coverage']):>7s} "
            f"{_pct(d['selective_accuracy']):>10s} {_pct(d['binary']['disease_missed']):>7s} │ "
            f"{r['ece']:5.3f}"
        )
    lines.append("ratés = images malades déclarées saines ; couv. = part des images décidées")
    return "\n".join(lines)


def _flat_metrics(results: dict[str, Any]) -> dict[str, float]:
    flat: dict[str, float] = {
        "decision.tau": results["decision_rule"]["tau"],
        "decision.tau_healthy": results["decision_rule"]["tau_healthy"],
    }
    for split, r in results["splits"].items():
        for mode in ("argmax", "decision"):
            m = r[mode]
            values = {
                "accuracy": m["accuracy"],
                "macro_f1": m["macro_f1"],
                "coverage": m["coverage"],
                "selective_accuracy": m["selective_accuracy"],
                "disease_missed": m["binary"]["disease_missed"],
                "disease_detected": m["binary"]["disease_detected"],
            }
            flat.update({f"{split}/{mode}.{k}": v for k, v in values.items() if v is not None})
        flat[f"{split}/ece"] = r["ece"]
    return flat


# ---------------------------------------------------------------------------
# Points d'entrée (appelés par `agridrone train` et `agridrone evaluate`)
# ---------------------------------------------------------------------------


def train(cfg: ExperimentConfig, *, root: Path | None = None) -> Path:
    """Entraîne, sélectionne le meilleur modèle, calibre et évalue. Renvoie le dossier du run."""
    if not isinstance(cfg, ClassificationExperiment):
        raise TypeError(f"config de tâche {cfg.task!r}, attendu 'classification'")
    ctx = init_run(cfg, root=root)
    device, t = ctx.device, cfg.train
    data_dir = resolve_path(cfg.data.dir, ctx.root)
    manifest = read_manifest(data_dir)
    classes = cfg.data.classes
    healthy = classes.index(cfg.data.healthy_class)
    print(f"Run : {ctx.run_dir}\nDevice : {device}", flush=True)

    model = build_classifier(
        cfg.model.arch,
        len(classes),
        pretrained=cfg.model.pretrained,
        drop_rate=cfg.model.drop_rate,
        drop_path_rate=cfg.model.drop_path_rate,
    )
    mean, std = normalization(model)
    model.to(device)
    size = cfg.model.input_size
    train_files, train_labels = classification_split(
        manifest, data_dir, cfg.data.train_split, classes
    )
    val_files, val_labels = classification_split(manifest, data_dir, cfg.data.val_split, classes)
    train_set = ClassificationDataset(
        train_files,
        train_labels,
        rgb_train_transform(size, seed=cfg.seed),
        mean=mean,
        std=std,
        decode_size=2 * size,  # marge pour le recadrage aléatoire
    )
    val_set = ClassificationDataset(
        val_files, val_labels, rgb_eval_transform(size), mean=mean, std=std, decode_size=size
    )
    pin = device.type == "cuda"
    train_loader = make_loader(
        train_set,
        batch_size=t.batch_size,
        shuffle=True,
        drop_last=len(train_set) > t.batch_size,  # pas de lot d'une image (BatchNorm)
        num_workers=cfg.num_workers,
        seed=cfg.seed,
        pin_memory=pin,
    )
    val_loader = make_loader(
        val_set,
        batch_size=cfg.eval.batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        seed=cfg.seed,
        pin_memory=pin,
    )

    weights = balanced_class_weights(train_labels, len(classes))
    criterion = nn.CrossEntropyLoss(
        weight=weights.to(device) if t.class_weights == "balanced" else None,
        label_smoothing=t.label_smoothing,
    )
    from timm.optim import create_optimizer_v2

    # AdamW ; pas de weight decay sur les biais et les normalisations.
    optimizer = create_optimizer_v2(model, opt="adamw", lr=t.lr, weight_decay=t.weight_decay)
    total_steps = t.epochs * len(train_loader)
    warmup_steps = min(round(t.warmup_epochs * len(train_loader)), total_steps)
    scheduler = LambdaLR(optimizer, warmup_cosine(warmup_steps, total_steps, t.min_lr_ratio))

    checkpoint_path = ctx.run_dir / "best.pt"
    history: list[dict[str, float]] = []
    best_f1, best_loss, stale = -math.inf, math.inf, 0
    print(
        f"Entraînement : {len(train_set)} images, validation : {len(val_set)}, "
        f"{len(train_loader)} lots/époque, "
        f"poids de classes {[round(w, 2) for w in weights.tolist()]}",
        flush=True,
    )
    with tracking_run(ctx) as run:
        if run is not None:
            import mlflow
        for epoch in range(1, t.epochs + 1):
            start = time.perf_counter()
            lr = optimizer.param_groups[0]["lr"]
            train_loss = _train_one_epoch(
                model, train_loader, criterion, optimizer, scheduler, device, t.precision
            )
            probs, y = predict(model, val_loader, device, t.precision)
            val = summarize_predictions(y, probs.argmax(axis=1), classes, healthy)
            record = {
                "epoch": epoch,
                "lr": lr,
                "train_loss": train_loss,
                "val_loss": _nll(probs, y),
                "val_accuracy": val["accuracy"],
                "val_macro_f1": val["macro_f1"],
                "seconds": time.perf_counter() - start,
            }
            history.append(record)
            f1, loss = record["val_macro_f1"], record["val_loss"]
            improved = f1 > best_f1 + 1e-9 or (abs(f1 - best_f1) <= 1e-9 and loss < best_loss)
            if improved:
                best_f1, best_loss, stale = f1, loss, 0
                ClassifierCheckpoint.from_model(
                    model,
                    arch=cfg.model.arch,
                    classes=list(classes),
                    input_size=size,
                    mean=mean,
                    std=std,
                    metadata={
                        "epoch": epoch,
                        "val_macro_f1": f1,
                        "config_hash": ctx.config_hash,
                        "run": ctx.run_dir.name,
                    },
                ).save(checkpoint_path)
            else:
                stale += 1
            if run is not None:
                mlflow.log_metrics({k: v for k, v in record.items() if k != "epoch"}, step=epoch)
            print(
                f"époque {epoch:3d}/{t.epochs}  perte {train_loss:.4f}  "
                f"val : perte {loss:.4f}  exact. {record['val_accuracy']:.3f}  "
                f"F1 macro {f1:.3f}{'  *' if improved else ''}  ({record['seconds']:.0f} s)",
                flush=True,
            )
            if t.patience is not None and stale >= t.patience:
                print(f"Arrêt anticipé : {t.patience} époques sans progrès.", flush=True)
                break

        pd.DataFrame(history).to_csv(ctx.run_dir / "history.csv", index=False)
        plot_history(history, ctx.run_dir / "history.png", metric="val_macro_f1")

        ckpt = ClassifierCheckpoint.load(checkpoint_path)
        print(f"Évaluation du meilleur modèle (époque {ckpt.metadata['epoch']})…", flush=True)
        results = run_evaluation(cfg, ckpt, ctx.run_dir / "eval", device, root=ctx.root)
        ckpt.decision = results["decision_rule"]
        ckpt.save(checkpoint_path)  # le checkpoint porte sa règle de décision

        if run is not None:
            mlflow.log_metrics(_flat_metrics(results))
            mlflow.log_metric("best_epoch", ckpt.metadata["epoch"])
            for name in ("history.csv", "history.png", "best.pt"):
                mlflow.log_artifact(str(ctx.run_dir / name))
            mlflow.log_artifacts(str(ctx.run_dir / "eval"), artifact_path="eval")
    print(format_results(results), flush=True)
    return ctx.run_dir


def evaluate(
    cfg: ExperimentConfig,
    run_dir: Path,
    *,
    out_dir: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    """Réévalue ``run_dir/best.pt`` (seuils recalibrés selon ``cfg.eval``).

    Le checkpoint n'est pas modifié ; les résultats vont dans ``out_dir``
    (par défaut ``run_dir/eval-<date>``).
    """
    if not isinstance(cfg, ClassificationExperiment):
        raise TypeError(f"config de tâche {cfg.task!r}, attendu 'classification'")
    root = root or project_root()
    device = resolve_device(cfg.device)
    out_dir = out_dir or run_dir / f"eval-{datetime.now():%Y%m%d-%H%M%S}"
    ckpt = ClassifierCheckpoint.load(run_dir / "best.pt")
    results = run_evaluation(cfg, ckpt, out_dir, device, root=root)
    print(format_results(results), flush=True)
    print(f"Résultats : {out_dir}", flush=True)
    return results
