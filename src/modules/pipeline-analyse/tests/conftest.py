"""Fixtures : un vol de démonstration complet, recréé dans un dossier temporaire pour chaque test."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ICI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ICI))
sys.path.insert(0, str(ICI / "outils"))

import creer_vol_demo  # noqa: E402
from analyse import Options  # noqa: E402

_CACHE: dict[str, Path] = {}


@pytest.fixture
def demo(tmp_path_factory, tmp_path) -> Path:
    """Copie fraîche d'un vol de démo (généré une seule fois par session, ~5 s)."""
    if "demo" not in _CACHE:
        racine = tmp_path_factory.mktemp("demo_source")
        creer_vol_demo.creer(racine, 9001, "ble", alerte_critique=True)
        _CACHE["demo"] = racine
    cible = tmp_path / "demo"
    shutil.copytree(_CACHE["demo"], cible)
    return cible


def options(racine: Path, registre: Path | None = None, **kw) -> Options:
    return Options(dossier_vol=racine / "vols" / "entrant" / "mission_09001_01",
                   dossier_missions=racine / "missions",
                   registre=registre or ICI / "modeles_demo.json",
                   dossier_sortie=racine / "vols", silencieux=True, **kw)


def lire_mission(racine: Path) -> dict:
    return json.loads((racine / "missions" / "mission_9001.json").read_text(encoding="utf-8"))


def ecrire_mission(racine: Path, donnees: dict, nom: str = "mission_9001.json") -> Path:
    p = racine / "missions" / nom
    p.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    return p
