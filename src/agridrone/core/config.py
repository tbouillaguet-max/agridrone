"""Configs YAML reproductibles.

Principes
---------
* **Héritage** : la clé ``_base_`` (chemin ou liste de chemins, relatifs au
  fichier qui la contient) désigne les configs parentes. Elles sont fusionnées
  dans l'ordre, puis le fichier courant par-dessus. Les dictionnaires sont
  fusionnés récursivement ; les listes et scalaires sont remplacés.
* **Surcharges** en ligne de commande : ``cle.sous_cle=valeur``, la valeur étant
  interprétée en YAML (``1e-3`` -> float, ``true`` -> bool, ``[1,2]`` -> liste).
* **Validation stricte** par un schéma pydantic : une clé inconnue (faute de
  frappe) est une erreur, jamais ignorée en silence.
* **Empreinte** : :func:`config_hash` identifie une config résolue, quel que
  soit l'ordre des clés ; elle est enregistrée avec chaque run.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

BASE_KEY = "_base_"


class ConfigError(ValueError):
    """Config introuvable, mal formée ou invalide."""


# ---------------------------------------------------------------------------
# Lecture YAML
# ---------------------------------------------------------------------------


class _Loader(yaml.SafeLoader):
    """SafeLoader qui reconnaît ``1e-3`` comme un float.

    PyYAML suit YAML 1.1 et lit ``1e-3`` (sans point) comme une chaîne, piège
    classique pour les learning rates. On ajoute la forme YAML 1.2.
    """


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?(?:[0-9][0-9_]*)(?:\.[0-9_]*)?[eE][-+]?[0-9]+$"),
    list("-+0123456789"),
)


def parse_yaml(text: str) -> Any:
    """Interprète une chaîne YAML avec le loader du projet."""
    return yaml.load(text, Loader=_Loader)  # _Loader dérive de SafeLoader : pas d'exécution


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Lit un fichier YAML dont la racine doit être un dictionnaire."""
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"Fichier de config introuvable : {p}")
    data = parse_yaml(p.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{p} : la racine doit être un dictionnaire, pas {type(data).__name__}")
    return data


def dump_yaml(data: Mapping[str, Any], path: str | Path) -> Path:
    """Écrit un dictionnaire en YAML lisible (ordre des clés conservé)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(dict(data), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Fusion, héritage, surcharges
# ---------------------------------------------------------------------------


def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Fusionne ``override`` dans ``base`` sans modifier les arguments."""
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _load_with_bases(path: Path, chain: tuple[Path, ...]) -> dict[str, Any]:
    path = path.resolve()
    if path in chain:
        cycle = " -> ".join(str(p) for p in (*chain, path))
        raise ConfigError(f"Héritage cyclique de configs : {cycle}")

    data = load_yaml(path)
    bases = data.pop(BASE_KEY, None)
    if bases is None:
        return data
    if isinstance(bases, str):
        bases = [bases]
    if not isinstance(bases, list) or not all(isinstance(b, str) for b in bases):
        raise ConfigError(f"{path} : '{BASE_KEY}' doit être un chemin ou une liste de chemins")

    merged: dict[str, Any] = {}
    for base in bases:
        merged = deep_merge(merged, _load_with_bases(path.parent / base, (*chain, path)))
    return deep_merge(merged, data)


def parse_override(text: str) -> tuple[list[str], Any]:
    """Découpe ``"a.b.c=valeur"`` en (``["a", "b", "c"]``, valeur interprétée)."""
    key, sep, raw_value = text.partition("=")
    keys = key.strip().split(".")
    if not sep or not all(keys):
        raise ConfigError(f"Surcharge invalide {text!r} : format attendu cle.sous_cle=valeur")
    try:
        value = parse_yaml(raw_value)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Surcharge invalide {text!r} : {exc}") from exc
    return keys, value


def apply_overrides(cfg: Mapping[str, Any], overrides: Iterable[str]) -> dict[str, Any]:
    """Applique des surcharges ``cle.sous_cle=valeur`` (crée les clés absentes ;
    les clés inconnues seront rejetées à la validation)."""
    result = deep_merge({}, cfg)
    for text in overrides:
        keys, value = parse_override(text)
        node = result
        for depth, k in enumerate(keys[:-1]):
            child = node.get(k)
            if child is None:
                child = node[k] = {}
            elif not isinstance(child, dict):
                path = ".".join(keys[: depth + 1])
                raise ConfigError(f"Surcharge {text!r} : '{path}' n'est pas une section")
            else:
                child = node[k] = dict(child)
            node = child
        node[keys[-1]] = value
    return result


def load_config(path: str | Path, overrides: Iterable[str] = ()) -> dict[str, Any]:
    """Charge une config (héritage résolu) puis applique les surcharges."""
    return apply_overrides(_load_with_bases(Path(path), ()), overrides)


def config_hash(cfg: Mapping[str, Any]) -> str:
    """Empreinte SHA-256 stable (indépendante de l'ordre des clés)."""
    canonical = json.dumps(cfg, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    """Base des sections de config : toute clé inconnue est une erreur."""

    model_config = ConfigDict(extra="forbid")


class PathsConfig(StrictModel):
    raw: Path = Path("data/raw")
    interim: Path = Path("data/interim")
    processed: Path = Path("data/processed")
    runs: Path = Path("runs")


class TrackingConfig(StrictModel):
    enabled: bool = True
    # Chemin sqlite relatif => résolu par rapport à la racine du projet.
    uri: str = "sqlite:///mlflow.db"
    experiment: str = "agridrone"
    # Artefacts MLflow (modèles, figures) ; un sous-dossier par expérience.
    artifact_root: Path = Path("mlartifacts")


class ExperimentConfig(StrictModel):
    """Champs communs à toutes les expériences ; les tâches l'étendent."""

    project: str = "agridrone"
    task: str = "base"
    name: str = "default"
    seed: int = 42
    # True : algorithmes déterministes PyTorch (plus lent ; voir core.seed).
    deterministic: bool = False
    device: str = Field(default="auto", pattern=r"^(auto|cpu|mps|cuda(:\d+)?)$")
    num_workers: int = Field(default=4, ge=0)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)


SchemaT = TypeVar("SchemaT", bound=type[ExperimentConfig])

TASK_SCHEMAS: dict[str, type[ExperimentConfig]] = {"base": ExperimentConfig}


def register_task_schema(task: str) -> Callable[[SchemaT], SchemaT]:
    """Décorateur : associe un schéma de config à une valeur de ``task``."""

    def decorator(schema: SchemaT) -> SchemaT:
        TASK_SCHEMAS[task] = schema
        return schema

    return decorator


def validate_config(raw: Mapping[str, Any]) -> ExperimentConfig:
    """Valide une config brute avec le schéma correspondant à sa ``task``."""
    task = raw.get("task", "base")
    schema = TASK_SCHEMAS.get(task) if isinstance(task, str) else None
    if schema is None:
        known = ", ".join(sorted(TASK_SCHEMAS))
        raise ConfigError(f"Tâche inconnue {task!r} (connues : {known})")
    try:
        return schema.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(f"Config invalide pour la tâche {task!r} :\n{exc}") from exc


def load_experiment(path: str | Path, overrides: Iterable[str] = ()) -> ExperimentConfig:
    """Charge, surcharge et valide une config d'expérience."""
    return validate_config(load_config(path, overrides))
