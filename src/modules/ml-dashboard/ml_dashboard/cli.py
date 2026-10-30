"""Interface en ligne de commande : ``python -m ml_dashboard <commande>``.

Commandes disponibles :

* ``validate <chemin> [...]`` : valide un run, un dossier de projet ou le
  dossier central (tous les runs trouvés sont validés).

Codes de sortie : 0 = tout est valide, 1 = au moins un run invalide,
2 = aucun run trouvé ou mauvaise utilisation.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .standard import SCHEMA_VERSION
from .validate import find_runs, validate_run


def _configure_console() -> None:
    """Évite les plantages d'encodage dans les vieilles consoles Windows."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def _cmd_validate(args: argparse.Namespace) -> int:
    runs: list[Path] = []
    for raw in args.paths:
        found = find_runs(raw)
        if not found:
            print(f"Aucun run (meta.json) trouvé sous : {raw}", file=sys.stderr)
        runs.extend(found)
    if not runs:
        return 2

    reports = [validate_run(r) for r in runs]
    failed = [r for r in reports if not r.ok or (args.strict and r.warnings)]

    if args.json:
        print(json.dumps([r.to_dict() for r in reports], ensure_ascii=False, indent=2))
    else:
        for r in reports:
            if args.quiet and r.ok and not r.warnings:
                continue
            print(r.format())
        print(f"\n{len(reports) - len(failed)}/{len(reports)} run(s) valide(s)"
              + (" (mode strict : alertes = erreurs)" if args.strict else ""))
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ml_dashboard",
        description="Standard de run ML : validation, import et dashboard.",
    )
    parser.add_argument("--version", action="version",
                        version=f"ml_dashboard {__version__} (schema_version {SCHEMA_VERSION})")
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate", help="valide un ou plusieurs dossiers de run")
    p_val.add_argument("paths", nargs="+", help="run, dossier de projet ou dossier central des runs")
    p_val.add_argument("--json", action="store_true", help="sortie JSON (pour scripts)")
    p_val.add_argument("--strict", action="store_true", help="les alertes font aussi échouer")
    p_val.add_argument("-q", "--quiet", action="store_true", help="n'affiche que les runs à problème")
    p_val.set_defaults(func=_cmd_validate)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    return int(args.func(args))
