"""Point d'entrée en ligne de commande : ``uv run agridrone <commande>``.

Commandes disponibles (chantier 0) :

* ``info``   — device détecté, versions des paquets, état git ;
* ``config`` — affiche une config résolue (héritage + surcharges) et validée ;
* ``smoke``  — run de bout en bout (graines, device, dossier de run, MLflow)
  sur un mini-modèle et des données aléatoires, pour valider l'installation.

Les surcharges s'écrivent ``cle.sous_cle=valeur`` après les options.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

import yaml

DEFAULT_CONFIG = "configs/base.yaml"


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"entier >= 1 attendu, reçu {text}")
    return value


def _cmd_info(args: argparse.Namespace) -> int:
    from agridrone.core.device import describe_device, resolve_device
    from agridrone.core.env import environment_snapshot
    from agridrone.core.paths import project_root

    root = project_root()
    report = {
        "project_root": str(root),
        **environment_snapshot(root),
        "device": describe_device(resolve_device(args.device)),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _cmd_config(args: argparse.Namespace) -> int:
    from agridrone.core.config import config_hash, load_experiment
    from agridrone.core.paths import resolve_path

    cfg = load_experiment(resolve_path(args.config), args.overrides).model_dump(mode="json")
    print(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), end="")
    print(f"# config_hash: {config_hash(cfg)}")
    return 0


def _cmd_smoke(args: argparse.Namespace) -> int:
    import torch
    from torch import nn

    from agridrone.core.config import load_experiment
    from agridrone.core.paths import resolve_path
    from agridrone.core.run import init_run, tracking_run

    cfg = load_experiment(resolve_path(args.config), args.overrides)
    ctx = init_run(cfg)
    print(f"Run : {ctx.run_dir}\nDevice : {ctx.device}")

    x = torch.randn(64, 3, 32, 32)
    y = torch.randint(0, 2, (64,))
    model = nn.Sequential(
        nn.Conv2d(3, 8, 3, padding=1),
        nn.ReLU(),
        nn.AdaptiveAvgPool2d(1),
        nn.Flatten(),
        nn.Linear(8, 2),
    ).to(ctx.device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    x, y = x.to(ctx.device), y.to(ctx.device)

    with tracking_run(ctx) as run:
        for step in range(args.steps):
            optimizer.zero_grad()
            loss = nn.functional.cross_entropy(model(x), y)
            loss.backward()
            optimizer.step()
            if run is not None:
                import mlflow

                mlflow.log_metric("loss", loss.item(), step=step)
    print(f"Perte finale : {loss.item():.6f} (identique d'un lancement à l'autre sur CPU)")
    if run is not None:
        print(f"MLflow : run {run.info.run_id} (voir `uv run mlflow ui`)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agridrone", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="device, versions, état git")
    p_info.add_argument("--device", default="auto", help="auto | cpu | mps | cuda[:N]")
    p_info.set_defaults(func=_cmd_info)

    for name, func, help_ in (
        ("config", _cmd_config, "affiche la config résolue"),
        ("smoke", _cmd_smoke, "run de vérification de bout en bout"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="fichier YAML")
        p.add_argument("overrides", nargs="*", help="surcharges cle.sous_cle=valeur")
        p.set_defaults(func=func)
        if name == "smoke":
            p.add_argument("--steps", type=_positive_int, default=20)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    from agridrone.core.config import ConfigError
    from agridrone.core.device import DeviceUnavailableError

    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (ConfigError, DeviceUnavailableError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
