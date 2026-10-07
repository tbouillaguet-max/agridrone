"""Export ONNX des modèles entraînés, vérification et mesure du temps d'inférence.

Le graphe exporté contient la normalisation (moyenne / écart-type par canal) et le
softmax : il prend des valeurs dans [0, 1] et rend des probabilités. L'embarqué n'a
donc ni statistiques à recopier ni ordre de bandes à deviner : tout est décrit dans
le fichier ``model.json`` écrit à côté du ``model.onnx`` (entrées, classes, règle de
décision, prétraitement).

Chaîne visée pour un Jetson (non mesurée ici, faute de matériel) : ``model.onnx`` →
TensorRT (``trtexec --onnx=model.onnx --fp16``) sur la cible, puis mesure sur place.
"""

from __future__ import annotations

import json
import platform
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from agridrone.core.device import Precision, autocast_context
from agridrone.models.classifier import ClassifierCheckpoint
from agridrone.models.segmenter import SegmenterCheckpoint

OPSET = 18


class ProbabilityModel(nn.Module):
    """Normalisation par canal + modèle + softmax sur l'axe des classes."""

    mean: torch.Tensor
    std: torch.Tensor

    def __init__(self, model: nn.Module, mean: list[float], std: list[float]) -> None:
        super().__init__()
        self.model = model
        self.register_buffer("mean", torch.tensor(mean, dtype=torch.float32).view(1, -1, 1, 1))
        self.register_buffer("std", torch.tensor(std, dtype=torch.float32).view(1, -1, 1, 1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        logits = self.model((x - self.mean) / self.std)
        return torch.softmax(logits, dim=1)


def _export(
    model: nn.Module,
    example: torch.Tensor,
    path: Path,
    dynamic: dict[int, str],
) -> Path:
    from torch.export import Dim

    shapes = {
        "x": {axis: Dim(name, min=1 if name == "batch" else 32) for axis, name in dynamic.items()}
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    program = torch.onnx.export(
        model,
        (example,),
        dynamo=True,
        dynamic_shapes=shapes,
        input_names=["input"],
        output_names=["probabilities"],
        opset_version=OPSET,
        external_data=False,
    )
    if program is None:  # seulement en mode TorchScript, jamais avec dynamo=True
        raise RuntimeError("l'export ONNX n'a pas produit de programme")
    program.save(str(path))
    return path


def export_classifier(ckpt: ClassifierCheckpoint, out_dir: Path) -> tuple[Path, ProbabilityModel]:
    """Exporte un classifieur : entrée (N, 3, S, S) RVB dans [0, 1], sortie (N, K)."""
    model = ProbabilityModel(ckpt.build_model(), ckpt.mean, ckpt.std).eval()
    size = ckpt.input_size
    path = _export(model, torch.rand(2, 3, size, size), out_dir / "model.onnx", {0: "batch"})
    describe = {
        "task": "classification",
        "architecture": ckpt.arch,
        "input": {
            "name": "input",
            "shape": ["batch", 3, size, size],
            "dtype": "float32",
            "range": [0.0, 1.0],
            "channels": ["red", "green", "blue"],
            "preprocessing": (
                f"plus petit côté ramené à {size} px (moyenne de surface, INTER_AREA), "
                f"puis recadrage central {size}×{size} ; normalisation incluse dans le graphe"
            ),
        },
        "output": {"name": "probabilities", "shape": ["batch", len(ckpt.classes)]},
        "classes": ckpt.classes,
        "decision": ckpt.decision,
        "decision_help": (
            "classe = argmax ; « incertain » si max < tau ; « sain » exige "
            "p[healthy_index] >= tau_healthy, sinon « incertain »"
        ),
        "metadata": ckpt.metadata,
    }
    (out_dir / "model.json").write_text(json.dumps(describe, indent=2, ensure_ascii=False))
    return path, model


def export_segmenter(ckpt: SegmenterCheckpoint, out_dir: Path) -> tuple[Path, ProbabilityModel]:
    """Exporte un U-Net : entrée (N, C, H, W) dans [0, 1] (H, W multiples de 32),
    sortie (N, K, H, W)."""
    model = ProbabilityModel(ckpt.build_model(), ckpt.mean, ckpt.std).eval()
    example = torch.rand(2, len(ckpt.bands), ckpt.tile, ckpt.tile)
    path = _export(model, example, out_dir / "model.onnx", {0: "batch", 2: "height", 3: "width"})
    describe = {
        "task": "segmentation",
        "encoder": ckpt.encoder,
        "input": {
            "name": "input",
            "shape": ["batch", len(ckpt.bands), "height", "width"],
            "dtype": "float32",
            "range": [0.0, 1.0],
            "bands": ckpt.bands,
            "constraints": "hauteur et largeur multiples de 32",
            "tiling": {"tile": ckpt.tile, "overlap": ckpt.overlap},
            "preprocessing": (
                "bandes dans l'ordre indiqué, valeurs ramenées dans [0, 1] comme à "
                "l'entraînement ; normalisation incluse dans le graphe"
            ),
        },
        "output": {
            "name": "probabilities",
            "shape": ["batch", len(ckpt.classes), "height", "width"],
        },
        "classes": ckpt.classes,
        "metadata": ckpt.metadata,
    }
    (out_dir / "model.json").write_text(json.dumps(describe, indent=2, ensure_ascii=False))
    return path, model


def onnx_session(path: Path, threads: int | None = None) -> Any:
    import onnxruntime as ort

    options = ort.SessionOptions()
    if threads is not None:
        options.intra_op_num_threads = threads
    return ort.InferenceSession(str(path), options, providers=["CPUExecutionProvider"])


def max_difference(path: Path, model: nn.Module, inputs: list[np.ndarray]) -> float:
    """Écart absolu maximal entre ONNX Runtime et PyTorch (float32) sur ``inputs``."""
    session = onnx_session(path)
    worst = 0.0
    with torch.inference_mode():
        for x in inputs:
            expected = model(torch.from_numpy(x)).numpy()
            got = session.run(None, {"input": x})[0]
            worst = max(worst, float(np.abs(expected - got).max()))
    return worst


def time_function(fn: Callable[[], Any], *, warmup: int = 3, repeat: int = 20) -> dict[str, float]:
    """Latence (ms) : médiane et 90e centile après ``warmup`` appels non comptés."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    return {
        "median_ms": statistics.median(times),
        "p90_ms": times[min(len(times) - 1, int(0.9 * len(times)))],
        "repeat": repeat,
    }


def benchmark(
    path: Path,
    model: nn.Module,
    input_shape: tuple[int, ...],
    batch_sizes: list[int],
    *,
    precisions: list[Precision] | None = None,
    repeat: int = 20,
) -> list[dict[str, Any]]:
    """Latence PyTorch (par précision) et ONNX Runtime (float32), CPU, par taille de lot."""
    precisions = precisions or ["fp32"]
    cpu = torch.device("cpu")
    session = onnx_session(path)
    rows: list[dict[str, Any]] = []
    for batch in batch_sizes:
        x = np.random.default_rng(0).random((batch, *input_shape), dtype=np.float32)
        tensor = torch.from_numpy(x)
        for precision in precisions:

            def run_torch(p: Precision = precision, t: torch.Tensor = tensor) -> None:
                with torch.inference_mode(), autocast_context(cpu, p):
                    model(t)

            rows.append(
                {
                    "runtime": f"PyTorch {torch.__version__} ({precision})",
                    "batch": batch,
                    **time_function(run_torch, repeat=repeat),
                }
            )

        def run_onnx(x: np.ndarray = x) -> None:
            session.run(None, {"input": x})

        rows.append(
            {
                "runtime": "ONNX Runtime (fp32)",
                "batch": batch,
                **time_function(run_onnx, repeat=repeat),
            }
        )
    for row in rows:
        row["images_per_second"] = 1000 * row["batch"] / row["median_ms"]
    return rows


def machine_description() -> dict[str, Any]:
    import os

    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "torch_threads": torch.get_num_threads(),
    }


def load_checkpoint(path: Path) -> ClassifierCheckpoint | SegmenterCheckpoint:
    """Charge un checkpoint de classifieur ou de segmenteur (d'après son format)."""
    try:
        return ClassifierCheckpoint.load(path)
    except ValueError:
        return SegmenterCheckpoint.load(path)


def count_gflops(model: nn.Module, input_shape: tuple[int, ...]) -> float:
    """GFLOPs (multiplications + additions) d'une inférence sur une image."""
    from torch.utils.flop_counter import FlopCounterMode

    counter = FlopCounterMode(display=False)
    with torch.inference_mode(), counter:
        model(torch.rand(1, *input_shape))
    return counter.get_total_flops() / 1e9


def export_run(
    run_dir: Path,
    out_dir: Path | None = None,
    *,
    batch_sizes: tuple[int, ...] = (1, 8),
    precisions: tuple[Precision, ...] = ("fp32", "bf16"),
    repeat: int = 20,
    measure: bool = True,
) -> dict[str, Any]:
    """Exporte ``run_dir/best.pt`` en ONNX, vérifie l'écart avec PyTorch, mesure les temps.

    Écrit ``model.onnx``, ``model.json`` et ``benchmark.json`` dans ``out_dir``
    (par défaut ``run_dir/export``).
    """
    out_dir = out_dir or run_dir / "export"
    ckpt = load_checkpoint(run_dir / "best.pt")
    if isinstance(ckpt, ClassifierCheckpoint):
        path, model = export_classifier(ckpt, out_dir)
        shape: tuple[int, ...] = (3, ckpt.input_size, ckpt.input_size)
    else:
        path, model = export_segmenter(ckpt, out_dir)
        shape = (len(ckpt.bands), ckpt.tile, ckpt.tile)
    rng = np.random.default_rng(0)
    inputs = [rng.random((n, *shape), dtype=np.float32) for n in (1, 2)]
    report: dict[str, Any] = {
        "onnx": path.name,
        "onnx_mb": path.stat().st_size / 1e6,
        "opset": OPSET,
        "input_shape": list(shape),
        "parameters_millions": sum(p.numel() for p in model.parameters()) / 1e6,
        "gflops_per_input": count_gflops(model, shape),
        "max_abs_diff_onnx_vs_pytorch": max_difference(path, model, inputs),
        "machine": machine_description(),
    }
    if measure:
        report["benchmark"] = benchmark(
            path, model, shape, list(batch_sizes), precisions=list(precisions), repeat=repeat
        )
    (out_dir / "benchmark.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"ONNX : {report['onnx']} ({report['onnx_mb']:.1f} Mo, opset {report['opset']}), "
        f"entrée {report['input_shape']}, {report['parameters_millions']:.1f} M paramètres, "
        f"{report['gflops_per_input']:.2f} GFLOPs par entrée",
        f"Écart max ONNX Runtime / PyTorch : {report['max_abs_diff_onnx_vs_pytorch']:.2e}",
    ]
    for row in report.get("benchmark", []):
        lines.append(
            f"  {row['runtime']:32s} lot {row['batch']:2d} : médiane {row['median_ms']:8.1f} ms, "
            f"p90 {row['p90_ms']:8.1f} ms, {row['images_per_second']:7.1f} entrées/s"
        )
    return "\n".join(lines)
