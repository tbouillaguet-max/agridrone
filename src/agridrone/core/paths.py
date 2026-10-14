"""Résolution des chemins du projet.

Tous les chemins relatifs des configs sont résolus par rapport à la racine du
projet (et non au répertoire courant), pour qu'une même config donne les mêmes
chemins quel que soit l'endroit d'où l'on lance la commande.

Le dépôt contient deux projets séparés, un par culture : ``ble/`` et ``olivier/``.
Chacun a ses configs, son registre de sources, ses rapports, son fichier de licences,
ses données (``data/<projet>/``) et ses runs (``runs/<projet>/``). :data:`PROJECTS`
décrit cet emplacement.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_ENV_VAR = "AGRIDRONE_ROOT"
_ROOT_MARKERS = ("pyproject.toml", "configs")


def project_root(start: Path | None = None) -> Path:
    """Renvoie la racine du projet.

    Ordre de priorité :
    1. la variable d'environnement ``AGRIDRONE_ROOT`` ;
    2. le premier dossier parent de ``start`` (défaut : répertoire courant)
       contenant à la fois ``pyproject.toml`` et ``configs/`` ;
    3. à défaut, le répertoire courant.
    """
    env_root = os.environ.get(ROOT_ENV_VAR)
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if all((candidate / marker).exists() for marker in _ROOT_MARKERS):
            return candidate
    return here


def resolve_path(path: str | Path, root: Path | None = None) -> Path:
    """Rend un chemin absolu : inchangé s'il l'est déjà, sinon relatif à la racine."""
    p = Path(path).expanduser()
    if p.is_absolute():
        return p
    return (root or project_root()) / p


@dataclass(frozen=True)
class Project:
    """Un projet du dépôt (une culture) et l'emplacement de ses fichiers."""

    name: str  #: nom du dossier : ``ble`` ou ``olivier``
    title: str  #: titre affiché : « BLÉ », « OLIVIER »

    @property
    def config(self) -> str:
        """Config de base du projet (dossiers des données et des runs)."""
        return f"{self.name}/configs/base.yaml"

    @property
    def registry(self) -> str:
        return f"{self.name}/configs/data/sources.yaml"

    @property
    def lock(self) -> str:
        return f"{self.name}/configs/data/sources.lock.yaml"

    @property
    def licences(self) -> str:
        return f"{self.name}/LICENCES_DONNEES.txt"


PROJECTS: dict[str, Project] = {
    "ble": Project("ble", "BLÉ"),
    "olivier": Project("olivier", "OLIVIER"),
}
