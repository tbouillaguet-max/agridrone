"""Point d'entrée en ligne de commande : ``uv run agridrone <commande>``.

Commandes disponibles (chantier 0) :

* ``info``   — device détecté, versions des paquets, état git ;
* ``config`` — affiche une config résolue (héritage + surcharges) et validée ;
* ``smoke``  — run de bout en bout (graines, device, dossier de run, MLflow)
  sur un mini-modèle et des données aléatoires, pour valider l'installation.

Données (chantier 2) :

* ``data list``     — sources du registre, statut et licence ;
* ``data download`` — téléchargement idempotent, vérification, extraction ;
* ``data verify``   — revérifie les empreintes des fichiers déjà téléchargés ;
* ``data prepare-classification`` — jeu « dossiers par classe » + manifeste ;
* ``data prepare-segmentation`` — jeux N bandes (.npy + masques) et tuilage d'orthophotos.

Modèles (chantiers 4 et suivants) :

* ``train``    — entraîne puis évalue ; la tâche est lue dans la config (``task``) ;
* ``evaluate`` — réévalue le meilleur modèle d'un run (``--run runs/<tâche>/<run>``).

Les surcharges s'écrivent ``cle.sous_cle=valeur`` après les options.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

import yaml

DEFAULT_CONFIG = "configs/base.yaml"
DEFAULT_REGISTRY = "configs/data/sources.yaml"
DEFAULT_LOCK = "configs/data/sources.lock.yaml"


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


def _cmd_train(args: argparse.Namespace) -> int:
    from agridrone.core.config import load_experiment, task_module
    from agridrone.core.paths import resolve_path

    cfg = load_experiment(resolve_path(args.config), args.overrides)
    run_dir = task_module(cfg.task).train(cfg)
    print(f"Run terminé : {run_dir}")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from pathlib import Path

    from agridrone.core.config import ConfigError, load_experiment, task_module
    from agridrone.core.paths import resolve_path

    run_dir = resolve_path(args.run)
    if not (run_dir / "config.yaml").is_file():
        raise ConfigError(f"{run_dir} n'est pas un dossier de run (config.yaml absent)")
    cfg = load_experiment(run_dir / "config.yaml", args.overrides)
    out = Path(args.out).resolve() if args.out else None
    task_module(cfg.task).evaluate(cfg, run_dir, out_dir=out)
    return 0


def _data_context(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    from agridrone.core.config import load_experiment
    from agridrone.core.paths import resolve_path
    from agridrone.data.sources import LockFile, load_registry

    cfg = load_experiment(resolve_path(args.config))
    registry = load_registry(resolve_path(args.registry))
    lock = LockFile(resolve_path(DEFAULT_LOCK))
    return registry, lock, resolve_path(cfg.paths.raw), resolve_path(cfg.paths.interim)


def _cmd_data_list(args: argparse.Namespace) -> int:
    registry, lock, raw_dir, _ = _data_context(args)
    for source_id, src in registry.sources.items():
        size = sum(
            f.size or (lock.get(f"{source_id}/{f.name}") or {}).get("size", 0) for f in src.files
        )
        present = all((raw_dir / source_id / f.name).exists() for f in src.files) and src.files
        print(
            f"{source_id:28s} {src.status:9s} {src.license:22s} {src.task:14s} "
            f"{size / 1e9:6.2f} Go {'téléchargé' if present else ''}"
        )
    return 0


def _cmd_data_download(args: argparse.Namespace) -> int:
    from agridrone.data.sources import fetch_source

    registry, lock, raw_dir, interim_dir = _data_context(args)
    lock.prune(registry)
    failures: dict[str, str] = {}
    for source_id, src in registry.selected(args.ids, args.include_candidates).items():
        print(f"[{source_id}] {src.title} ({src.license}, {src.status})", flush=True)
        try:
            results = fetch_source(
                source_id,
                src,
                raw_dir,
                interim_dir,
                lock,
                extract=not args.no_extract,
                progress=True,
            )
        except Exception as exc:  # une source en échec ne bloque pas les suivantes
            failures[source_id] = f"{type(exc).__name__}: {exc}"
            print(f"   ÉCHEC : {failures[source_id]}", file=sys.stderr, flush=True)
            continue
        for r in results:
            digest, size_mb = r.digests.sha256[:16], r.digests.size / 1e6
            print(f"   {r.status:10s} {r.path.name}  sha256={digest}…  {size_mb:.1f} Mo")
    if failures:
        print(f"{len(failures)} source(s) en échec : {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def _cmd_data_verify(args: argparse.Namespace) -> int:
    from agridrone.data.sources import IntegrityError, check_digests, file_digests

    registry, lock, raw_dir, _ = _data_context(args)
    failures = 0
    for source_id, src in registry.sources.items():
        for f in src.files:
            path = raw_dir / source_id / f.name
            if not path.exists():
                continue
            try:
                check_digests(file_digests(path), f, lock.get(f"{source_id}/{f.name}"))
                print(f"OK      {source_id}/{f.name}")
            except IntegrityError as exc:
                failures += 1
                print(f"ÉCHEC   {exc}")
    return 1 if failures else 0


def _cmd_data_prepare_classification(args: argparse.Namespace) -> int:
    from agridrone.core.config import load_experiment
    from agridrone.core.paths import resolve_path
    from agridrone.data.classification import (
        load_classification_config,
        prepare_classification,
        summarize,
    )

    cfg = load_experiment(resolve_path(args.config))
    data_cfg = load_classification_config(resolve_path(args.data_config))
    out_dir = resolve_path(cfg.paths.processed) / "classification"
    df = prepare_classification(data_cfg, resolve_path(cfg.paths.interim), out_dir)
    summary = summarize(df)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Jeu écrit dans {out_dir}")
    return 0


def _cmd_data_prepare_segmentation(args: argparse.Namespace) -> int:
    from agridrone.core.config import load_experiment, load_yaml
    from agridrone.core.paths import project_root, resolve_path
    from agridrone.data.segmentation import SegmentationDataConfig, prepare_segmentation

    cfg = load_experiment(resolve_path(args.config))
    data_cfg = SegmentationDataConfig.model_validate(load_yaml(resolve_path(args.data_config)))
    out = resolve_path(cfg.paths.processed) / "segmentation"
    results = prepare_segmentation(data_cfg, resolve_path(cfg.paths.interim), out, project_root())
    for name, df in results.items():
        print(f"{name:40s} {len(df):6d} éléments  {df['split'].value_counts().to_dict()}")
    print(f"Jeux écrits dans {out}")
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

    p = sub.add_parser("train", help="entraîne puis évalue (tâche lue dans la config)")
    p.add_argument("-c", "--config", required=True, help="fichier YAML de l'expérience")
    p.add_argument("overrides", nargs="*", help="surcharges cle.sous_cle=valeur")
    p.set_defaults(func=_cmd_train)

    p = sub.add_parser("evaluate", help="réévalue le meilleur modèle d'un run")
    p.add_argument("--run", required=True, help="dossier du run (runs/<tâche>/<run>)")
    p.add_argument("--out", help="dossier des résultats (défaut : <run>/eval-<date>)")
    p.add_argument("overrides", nargs="*", help="surcharges, ex. eval.target_coverage=0.8")
    p.set_defaults(func=_cmd_evaluate)

    p_data = sub.add_parser("data", help="sources de données (chantier 2)")
    data_sub = p_data.add_subparsers(dest="data_command", required=True)
    for name, func, help_ in (
        ("list", _cmd_data_list, "sources du registre"),
        ("download", _cmd_data_download, "télécharge, vérifie et extrait"),
        ("verify", _cmd_data_verify, "revérifie les fichiers téléchargés"),
    ):
        p = data_sub.add_parser(name, help=help_)
        p.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="config (chemins)")
        p.add_argument("--registry", default=DEFAULT_REGISTRY, help="registre des sources")
        p.set_defaults(func=func)
        if name == "download":
            p.add_argument("ids", nargs="*", help="sources (défaut : toutes les retenues)")
            p.add_argument("--include-candidates", action="store_true")
            p.add_argument("--no-extract", action="store_true", help="ne pas extraire les archives")
    p = data_sub.add_parser("prepare-classification", help="jeu « dossiers par classe »")
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="config (chemins)")
    p.add_argument("--data-config", default="configs/data/classification.yaml")
    p.set_defaults(func=_cmd_data_prepare_classification)
    p = data_sub.add_parser("prepare-segmentation", help="jeux multispectraux N bandes + tuilage")
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="config (chemins)")
    p.add_argument("--data-config", default="configs/data/segmentation.yaml")
    p.set_defaults(func=_cmd_data_prepare_segmentation)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import requests

    from agridrone.core.config import ConfigError
    from agridrone.core.device import DeviceUnavailableError
    from agridrone.data.sources import IntegrityError, UnsafeArchiveError

    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (
        ConfigError,
        DeviceUnavailableError,
        IntegrityError,
        UnsafeArchiveError,
        requests.RequestException,
    ) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    raise SystemExit(main())
