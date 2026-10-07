"""Segmentation multispectrale N bandes : U-Net contre baselines par indices (chantier 5).

Jeu : WeedsGalore (fond / culture / adventice, découpage officiel spatial), préparé par
``agridrone data prepare-segmentation``. Le nombre de bandes d'entrée vient de la
config (``data.bands``, par nom) : le même code sert à 3, 4, 5… N bandes.

1. U-Net (encodeur timm pré-entraîné) entraîné sur des recadrages aléatoires,
   sélectionné sur le mIoU de validation (inférence par tuiles, comme sur une
   orthomosaïque) ;
2. baselines NDVI / NDRE (Otsu, multi-Otsu, seuil supervisé) dont les seuils sont
   estimés sur l'ensemble d'entraînement ;
3. évaluation de tout cela sur val et test : IoU et F1 par classe, et sur la tâche
   fusionnée fond / végétation, la seule que les seuils d'indice savent traiter.

Sorties dans le dossier du run : ``best.pt``, ``history.csv`` / ``history.png``,
``eval/metrics.json``, ``eval/iou_<ensemble>.png``, ``eval/exemples_<ensemble>.png``.
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
from agridrone.data.augment import multispectral_train_transform
from agridrone.data.datasets import SegmentationDataset, load_segmentation_sample
from agridrone.data.normalize import BandStats
from agridrone.eval.classification import SERIES_COLORS
from agridrone.eval.segmentation import (
    IGNORE_INDEX,
    false_color,
    merge_confusion,
    pixel_confusion,
    plot_examples,
    plot_iou_comparison,
    segmentation_scores,
)
from agridrone.models.indices import (
    INDEX_BANDS,
    IndexBaseline,
    accumulate_histograms,
    fit_index_baselines,
)
from agridrone.models.segmenter import SegmenterCheckpoint, build_unet, predict_tiled
from agridrone.training.common import make_loader, plot_history, warmup_cosine

VEGETATION = "végétation"

# ---------------------------------------------------------------------------
# Schéma de config
# ---------------------------------------------------------------------------


class SegmentationData(StrictModel):
    #: Jeu préparé : ``images/*.npy`` (C, H, W) dans [0, 1], ``masks/*.png``,
    #: ``index.csv`` (ensembles), ``dataset.json`` (noms des bandes et des classes).
    dir: Path = Path("data/processed/segmentation/weedsgalore")
    #: Bandes d'entrée du modèle, par nom et dans cet ordre. Vide : toutes les bandes.
    bands: list[str] = Field(default_factory=list)
    background_class: str = "background"
    #: Noms affichés et couleurs des classes dans les figures (ordre du jeu).
    display_names: dict[str, str] = Field(default_factory=dict)
    class_colors: list[str] = Field(default_factory=lambda: ["#d8d2c4", "#1baf7a", "#eb6834"])
    stats_file: str = "band_stats_train.json"
    train_split: str = "train"
    val_split: str = "val"
    test_splits: list[str] = Field(default_factory=lambda: ["test"])


class SegmenterModel(StrictModel):
    encoder: str = "tu-resnet18.a1_in1k"
    pretrained: bool = True


class SegmentationTrain(StrictModel):
    epochs: int = Field(default=40, ge=1)
    batch_size: int = Field(default=8, ge=2)
    lr: float = Field(default=5e-4, gt=0.0)
    weight_decay: float = Field(default=1e-4, ge=0.0)
    warmup_epochs: float = Field(default=1.0, ge=0.0)
    min_lr_ratio: float = Field(default=0.01, ge=0.0, le=1.0)
    #: Côté des recadrages aléatoires (multiple de 32).
    crop: int = Field(default=256, ge=32)
    #: Recadrages tirés par image et par époque.
    samples_per_image: int = Field(default=4, ge=1)
    #: Entropie croisée seule, ou + Dice (moins sensible au déséquilibre des classes).
    loss: Literal["ce", "ce_dice"] = "ce_dice"
    patience: int | None = Field(default=10, ge=1)
    precision: Precision = "fp32"

    @model_validator(mode="after")
    def _check_crop(self) -> SegmentationTrain:
        if self.crop % 32:
            raise ValueError(f"crop={self.crop} : un multiple de 32 est requis par le U-Net")
        return self


class SegmentationEval(StrictModel):
    #: Inférence par tuiles (côté multiple de 32) avec chevauchement.
    tile: int = Field(default=256, ge=32)
    overlap: int = Field(default=64, ge=0)
    batch_size: int = Field(default=8, ge=1)
    precision: Precision = "fp32"
    #: Indices évalués en baseline (s'ils sont calculables avec les bandes du jeu).
    baselines: list[str] = Field(default_factory=lambda: ["ndvi", "ndre"])
    #: Nombre d'images illustrées par ensemble.
    examples: int = Field(default=4, ge=0)


@register_task_schema("segmentation")
class SegmentationExperiment(ExperimentConfig):
    task: str = "segmentation"
    data: SegmentationData = Field(default_factory=SegmentationData)
    model: SegmenterModel = Field(default_factory=SegmenterModel)
    train: SegmentationTrain = Field(default_factory=SegmentationTrain)
    eval: SegmentationEval = Field(default_factory=SegmentationEval)


# ---------------------------------------------------------------------------
# Données
# ---------------------------------------------------------------------------


class SegmentationSet:
    """Jeu préparé : bandes et classes nommées, ensembles, statistiques d'entraînement."""

    def __init__(self, cfg: SegmentationExperiment, root: Path) -> None:
        self.dir = resolve_path(cfg.data.dir, root)
        info_path = self.dir / "dataset.json"
        if not info_path.is_file():
            raise FileNotFoundError(
                f"{info_path} introuvable : lancer `agridrone data prepare-segmentation`"
            )
        info = json.loads(info_path.read_text(encoding="utf-8"))
        self.all_bands: list[str] = list(info["bands"])
        self.classes: list[str] = list(info["classes"])
        self.bands = list(cfg.data.bands) or self.all_bands
        unknown = sorted(set(self.bands) - set(self.all_bands))
        if unknown:
            raise ValueError(f"bandes absentes du jeu {self.dir.name} : {unknown}")
        if cfg.data.background_class not in self.classes:
            raise ValueError(f"classe de fond {cfg.data.background_class!r} absente")
        if len(cfg.data.class_colors) < len(self.classes):
            raise ValueError("une couleur par classe attendue (data.class_colors)")
        self.background = self.classes.index(cfg.data.background_class)
        self.band_indices = [self.all_bands.index(b) for b in self.bands]
        self.index = pd.read_csv(self.dir / "index.csv")
        stats = BandStats.load(self.dir / cfg.data.stats_file)
        self.mean = [stats.mean[stats.bands.index(b)] for b in self.bands]
        self.std = [stats.std[stats.bands.index(b)] for b in self.bands]

    def samples(self, split: str) -> list[str]:
        names: list[str] = (
            self.index.loc[self.index["split"] == split, "sample"].astype(str).tolist()
        )
        if not names:
            raise ValueError(f"ensemble {split!r} vide dans {self.dir / 'index.csv'}")
        return names

    def load(self, sample: str) -> tuple[np.ndarray, np.ndarray]:
        """Image complète (toutes les bandes du jeu) et masque."""
        return load_segmentation_sample(self.dir, sample)

    def vegetation_groups(self) -> list[list[int]]:
        others = [i for i in range(len(self.classes)) if i != self.background]
        return [[self.background], others]


# ---------------------------------------------------------------------------
# Entraînement
# ---------------------------------------------------------------------------


def _criterion(kind: str) -> nn.Module:
    ce = nn.CrossEntropyLoss(ignore_index=IGNORE_INDEX)
    if kind == "ce":
        return ce
    import segmentation_models_pytorch as smp

    dice = smp.losses.DiceLoss(mode="multiclass", ignore_index=IGNORE_INDEX)

    class CeDice(nn.Module):
        def forward(self, logits: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
            loss: torch.Tensor = ce(logits, target) + dice(logits, target)
            return loss

    return CeDice()


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
        loss = criterion(logits.float(), y)
        loss.backward()
        optimizer.step()
        scheduler.step()
        total += loss.item() * len(y)
        count += len(y)
    return total / count


def _predict_split(
    model: nn.Module,
    data: SegmentationSet,
    split: str,
    cfg: SegmentationExperiment,
    normalization: tuple[list[float], list[float]],
    device: torch.device,
    precision: Precision,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Confusion cumulée (K, K) du modèle sur un ensemble, et prédictions par image."""
    k = len(data.classes)
    cm = np.zeros((k, k), np.int64)
    predictions: dict[str, np.ndarray] = {}
    mean = np.asarray(normalization[0], np.float32)[:, None, None]
    std = np.asarray(normalization[1], np.float32)[:, None, None]
    for sample in data.samples(split):
        image, mask = data.load(sample)
        x = (image[data.band_indices] - mean) / std
        probs = predict_tiled(
            model,
            x,
            tile=cfg.eval.tile,
            overlap=cfg.eval.overlap,
            device=device,
            precision=precision,
            batch_size=cfg.eval.batch_size,
        )
        pred = probs.argmax(axis=0).astype(np.uint8)
        cm += pixel_confusion(mask, pred, k)
        predictions[sample] = pred
    return cm, predictions


def _scores(cm: np.ndarray, data: SegmentationSet, classes: list[str]) -> dict[str, Any]:
    merged = merge_confusion(cm, data.vegetation_groups())
    return {
        "classes": segmentation_scores(cm, classes),
        "fond_vegetation": segmentation_scores(merged, [classes[data.background], VEGETATION]),
    }


def run_evaluation(
    cfg: SegmentationExperiment,
    ckpt: SegmenterCheckpoint,
    out_dir: Path,
    device: torch.device,
    *,
    root: Path,
) -> dict[str, Any]:
    """U-Net et baselines par indices sur val et test ; métriques et figures."""
    data = SegmentationSet(cfg, root)
    if ckpt.bands != data.bands or ckpt.classes != data.classes:
        raise ValueError("bandes ou classes du checkpoint différentes de celles de la config")
    model = ckpt.build_model().to(device)
    names = [cfg.data.display_names.get(c, c) for c in data.classes]
    splits = [cfg.data.val_split, *cfg.data.test_splits]

    # Baselines : histogrammes d'indice sur l'entraînement, toutes bandes du jeu.
    baselines: dict[str, IndexBaseline] = {}
    others = [i for i in range(len(data.classes)) if i != data.background]
    for index in cfg.eval.baselines:
        if not set(INDEX_BANDS[index]) <= set(data.all_bands):
            continue
        hists = accumulate_histograms(
            (data.load(s) for s in data.samples(cfg.data.train_split)),
            data.all_bands,
            index,
            len(data.classes),
        )
        baselines.update(
            fit_index_baselines(hists, index, background=data.background, vegetation=others)
        )

    results: dict[str, Any] = {
        "checkpoint": ckpt.metadata,
        "bands": ckpt.bands,
        "baselines": {
            name: {"index": b.index, "method": b.method, "thresholds": list(b.thresholds)}
            for name, b in baselines.items()
        },
        "splits": {},
    }
    unet_name = f"U-Net {len(ckpt.bands)} bandes"
    for split in splits:
        start = time.perf_counter()
        cm, predictions = _predict_split(
            model, data, split, cfg, (ckpt.mean, ckpt.std), device, cfg.eval.precision
        )
        seconds = time.perf_counter() - start
        split_result: dict[str, Any] = {
            "unet": {**_scores(cm, data, data.classes), "seconds": seconds},
            "baselines": {},
        }
        baseline_masks: dict[str, dict[str, np.ndarray]] = {name: {} for name in baselines}
        baseline_cms = {name: np.zeros_like(cm) for name in baselines}
        for sample in data.samples(split):
            image, mask = data.load(sample)
            for name, baseline in baselines.items():
                pred = baseline.predict(image, data.all_bands, nodata=data.background)
                baseline_cms[name] += pixel_confusion(mask, pred, len(data.classes))
                baseline_masks[name][sample] = pred
        for name, baseline in baselines.items():
            scores = _scores(baseline_cms[name], data, data.classes)
            if baseline.method != "multi_otsu":
                # Deux intervalles : seule la tâche fond / végétation a un sens.
                del scores["classes"]
            split_result["baselines"][name] = scores
        results["splits"][split] = split_result

        # Figure : IoU par classe et par méthode.
        unet_iou = {
            n: split_result["unet"]["classes"]["per_class"][c]["iou"]
            for n, c in zip(names, data.classes, strict=True)
        }
        unet_iou[VEGETATION] = split_result["unet"]["fond_vegetation"]["per_class"][VEGETATION][
            "iou"
        ]
        bars: dict[str, dict[str, float | None]] = {unet_name: unet_iou}
        for name, scores in split_result["baselines"].items():
            fv = scores["fond_vegetation"]["per_class"]
            values: dict[str, float | None] = dict.fromkeys(names)
            if "classes" in scores:
                for n, c in zip(names, data.classes, strict=True):
                    values[n] = scores["classes"]["per_class"][c]["iou"]
            values[names[data.background]] = fv[data.classes[data.background]]["iou"]
            values[VEGETATION] = fv[VEGETATION]["iou"]
            bars[name] = values
        if len(bars) <= len(SERIES_COLORS):
            plot_iou_comparison(
                bars,
                [*names, VEGETATION],
                out_dir / f"iou_{split}.png",
                title=f"IoU par classe · {split} · {ckpt.encoder}",
            )
        # Figure : exemples (fausses couleurs, vérité, U-Net, meilleure baseline à 3 classes).
        if cfg.eval.examples:
            three_class = [n for n, b in baselines.items() if b.method == "multi_otsu"]
            rows = []
            for sample in data.samples(split)[: cfg.eval.examples]:
                image, mask = data.load(sample)
                row = {
                    "image (PIR-R-V)": false_color(image, data.all_bands),
                    "vérité terrain": mask,
                    unet_name: predictions[sample],
                }
                for name in three_class[:1]:
                    row[name] = baseline_masks[name][sample]
                rows.append(row)
            plot_examples(
                rows,
                list(rows[0]),
                cfg.data.class_colors,
                names,
                out_dir / f"exemples_{split}.png",
                title=f"{split} : exemples",
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "metrics.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return results


def format_results(results: dict[str, Any]) -> str:
    """Tableau texte : mIoU et IoU par classe, puis tâche fond / végétation."""
    lines = []
    for split, r in results["splits"].items():
        u = r["unet"]
        per_class = u["classes"]["per_class"]
        cls = "  ".join(f"{c} {m['iou']:.3f}" for c, m in per_class.items() if m["iou"] is not None)
        veg = u["fond_vegetation"]["per_class"][VEGETATION]["iou"]
        lines.append(
            f"[{split}] U-Net : mIoU {u['classes']['miou']:.3f} ({cls}) ; végétation {veg:.3f}"
        )
        for name, b in r["baselines"].items():
            veg_b = b["fond_vegetation"]["per_class"][VEGETATION]["iou"]
            extra = f" ; mIoU 3 classes {b['classes']['miou']:.3f}" if "classes" in b else ""
            lines.append(f"[{split}]   {name:24s} végétation {veg_b:.3f}{extra}")
    return "\n".join(lines)


def _flat_metrics(results: dict[str, Any]) -> dict[str, float]:
    flat: dict[str, float] = {}
    for split, r in results["splits"].items():
        u = r["unet"]
        flat[f"{split}/unet.miou"] = u["classes"]["miou"]
        flat[f"{split}/unet.vegetation_iou"] = u["fond_vegetation"]["per_class"][VEGETATION]["iou"]
        for c, m in u["classes"]["per_class"].items():
            if m["iou"] is not None:
                flat[f"{split}/unet.iou.{c}"] = m["iou"]
        for name, b in r["baselines"].items():
            flat[f"{split}/{name}.vegetation_iou"] = b["fond_vegetation"]["per_class"][VEGETATION][
                "iou"
            ]
            if "classes" in b:
                flat[f"{split}/{name}.miou"] = b["classes"]["miou"]
    return flat


def train(cfg: ExperimentConfig, *, root: Path | None = None) -> Path:
    """Entraîne le U-Net, garde le meilleur (mIoU de validation), évalue avec les baselines."""
    if not isinstance(cfg, SegmentationExperiment):
        raise TypeError(f"config de tâche {cfg.task!r}, attendu 'segmentation'")
    ctx = init_run(cfg, root=root)
    device, t = ctx.device, cfg.train
    data = SegmentationSet(cfg, ctx.root)
    print(f"Run : {ctx.run_dir}\nDevice : {device}\nBandes : {data.bands}", flush=True)

    model = build_unet(
        cfg.model.encoder, len(data.bands), len(data.classes), pretrained=cfg.model.pretrained
    ).to(device)
    train_set = SegmentationDataset(
        data.dir,
        data.samples(cfg.data.train_split),
        data.band_indices,
        mean=data.mean,
        std=data.std,
        transform=multispectral_train_transform(crop=t.crop, seed=cfg.seed),
        samples_per_image=t.samples_per_image,
    )
    loader = make_loader(
        train_set,
        batch_size=t.batch_size,
        shuffle=True,
        drop_last=len(train_set) > t.batch_size,
        num_workers=cfg.num_workers,
        seed=cfg.seed,
        pin_memory=device.type == "cuda",
    )
    criterion = _criterion(t.loss)
    from timm.optim import create_optimizer_v2

    optimizer = create_optimizer_v2(model, opt="adamw", lr=t.lr, weight_decay=t.weight_decay)
    total_steps = t.epochs * len(loader)
    warmup_steps = min(round(t.warmup_epochs * len(loader)), total_steps)
    scheduler = LambdaLR(optimizer, warmup_cosine(warmup_steps, total_steps, t.min_lr_ratio))

    def snapshot(epoch: int, miou: float) -> SegmenterCheckpoint:
        return SegmenterCheckpoint.from_model(
            model,
            encoder=cfg.model.encoder,
            bands=list(data.bands),
            classes=list(data.classes),
            mean=list(data.mean),
            std=list(data.std),
            tile=cfg.eval.tile,
            overlap=cfg.eval.overlap,
            metadata={
                "epoch": epoch,
                "val_miou": miou,
                "config_hash": ctx.config_hash,
                "run": ctx.run_dir.name,
            },
        )

    checkpoint_path = ctx.run_dir / "best.pt"
    history: list[dict[str, float]] = []
    best, stale = -math.inf, 0
    print(
        f"Entraînement : {len(data.samples(cfg.data.train_split))} images × "
        f"{t.samples_per_image} recadrages {t.crop}², {len(loader)} lots/époque",
        flush=True,
    )
    with tracking_run(ctx) as run:
        for epoch in range(1, t.epochs + 1):
            start = time.perf_counter()
            lr = optimizer.param_groups[0]["lr"]
            train_loss = _train_one_epoch(
                model, loader, criterion, optimizer, scheduler, device, t.precision
            )
            cm, _ = _predict_split(
                model, data, cfg.data.val_split, cfg, (data.mean, data.std), device, t.precision
            )
            val = segmentation_scores(cm, data.classes)
            miou = float(val["miou"])
            record = {
                "epoch": epoch,
                "lr": lr,
                "train_loss": train_loss,
                "val_miou": miou,
                "val_pixel_accuracy": float(val["pixel_accuracy"]),
                "seconds": time.perf_counter() - start,
            }
            history.append(record)
            improved = miou > best + 1e-9
            if improved:
                best, stale = miou, 0
                snapshot(epoch, miou).save(checkpoint_path)
            else:
                stale += 1
            if run is not None:
                import mlflow

                mlflow.log_metrics({k: v for k, v in record.items() if k != "epoch"}, step=epoch)
            print(
                f"époque {epoch:3d}/{t.epochs}  perte {train_loss:.4f}  val : mIoU {miou:.3f}  "
                f"exact. pixel {record['val_pixel_accuracy']:.3f}"
                f"{'  *' if improved else ''}  ({record['seconds']:.0f} s)",
                flush=True,
            )
            if t.patience is not None and stale >= t.patience:
                print(f"Arrêt anticipé : {t.patience} époques sans progrès.", flush=True)
                break

        pd.DataFrame(history).to_csv(ctx.run_dir / "history.csv", index=False)
        plot_history(history, ctx.run_dir / "history.png", metric="val_miou")
        ckpt = SegmenterCheckpoint.load(checkpoint_path)
        print(f"Évaluation du meilleur modèle (époque {ckpt.metadata['epoch']})…", flush=True)
        results = run_evaluation(cfg, ckpt, ctx.run_dir / "eval", device, root=ctx.root)
        if run is not None:
            import mlflow

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
    """Réévalue ``run_dir/best.pt`` ; résultats dans ``out_dir`` (``run_dir/eval-<date>``)."""
    if not isinstance(cfg, SegmentationExperiment):
        raise TypeError(f"config de tâche {cfg.task!r}, attendu 'segmentation'")
    root = root or project_root()
    device = resolve_device(cfg.device)
    out_dir = out_dir or run_dir / f"eval-{datetime.now():%Y%m%d-%H%M%S}"
    ckpt = SegmenterCheckpoint.load(run_dir / "best.pt")
    results = run_evaluation(cfg, ckpt, out_dir, device, root=root)
    print(format_results(results), flush=True)
    print(f"Résultats : {out_dir}", flush=True)
    return results
