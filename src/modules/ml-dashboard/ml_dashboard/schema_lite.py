"""Validateur JSON Schema minimal (sous-ensemble du draft 2020-12).

Pourquoi ne pas utiliser ``jsonschema`` ? Pour respecter la contrainte « peu de
dépendances ». Les schémas de ``ml_dashboard/schemas`` restent des JSON Schema
standards : ils sont lisibles par n'importe quel outil externe, et ce module
n'en implémente que les mots-clés effectivement utilisés.

Mots-clés pris en charge : $ref (local, "#/$defs/..."), type, enum, const, required, properties,
additionalProperties, items, minItems, uniqueItems, pattern, minLength,
minimum, maximum, format ("date-time").
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from functools import lru_cache
from importlib import resources
from typing import Any

_TYPE_CHECKS: dict[str, Any] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    # bool est une sous-classe de int en Python : on l'exclut explicitement.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Charge un schéma embarqué dans le paquet (ex. ``"meta"``)."""
    text = resources.files("ml_dashboard.schemas").joinpath(f"{name}.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


def _fmt_path(path: str) -> str:
    return path or "(racine)"


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    """Résout une référence locale ``#/a/b`` dans le schéma racine."""
    if not ref.startswith("#/"):
        raise ValueError(f"Seules les références locales sont prises en charge : {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate_instance(
    instance: Any, schema: dict[str, Any], path: str = "", root: dict[str, Any] | None = None
) -> list[str]:
    """Valide ``instance`` contre ``schema`` et renvoie la liste des erreurs (vide si OK).

    Chaque erreur est préfixée par le chemin JSON de la valeur fautive,
    par exemple ``environment.gpu : type attendu string|null, reçu int``.
    """
    root = root if root is not None else schema
    if "$ref" in schema:
        schema = _resolve(schema["$ref"], root)
    errors: list[str] = []
    where = _fmt_path(path)

    # --- type ------------------------------------------------------------- #
    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_TYPE_CHECKS[t](instance) for t in types):
            errors.append(f"{where} : type attendu {'|'.join(types)}, reçu {type(instance).__name__}")
            return errors  # inutile de poursuivre sur une valeur du mauvais type

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{where} : valeur attendue {schema['const']!r}, reçu {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{where} : valeur {instance!r} hors de {schema['enum']}")

    # --- chaînes ---------------------------------------------------------- #
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{where} : chaîne trop courte (min {schema['minLength']})")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{where} : {instance!r} ne respecte pas le motif {schema['pattern']}")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(instance)
            except ValueError:
                errors.append(f"{where} : date ISO 8601 invalide {instance!r}")

    # --- nombres ---------------------------------------------------------- #
    if _TYPE_CHECKS["number"](instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{where} : {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{where} : {instance} > maximum {schema['maximum']}")

    # --- objets ----------------------------------------------------------- #
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{where} : clé obligatoire manquante {key!r}")
        props: dict[str, Any] = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, value in instance.items():
            child = f"{path}.{key}" if path else key
            if key in props:
                errors.extend(validate_instance(value, props[key], child, root))
            elif additional is False:
                errors.append(f"{where} : clé non autorisée {key!r}")
            elif isinstance(additional, dict):
                errors.extend(validate_instance(value, additional, child, root))

    # --- tableaux --------------------------------------------------------- #
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{where} : au moins {schema['minItems']} élément(s) attendu(s)")
        if schema.get("uniqueItems"):
            seen = [json.dumps(v, sort_keys=True) for v in instance]
            if len(seen) != len(set(seen)):
                errors.append(f"{where} : éléments en double")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors.extend(validate_instance(item, schema["items"], f"{path}[{i}]", root))

    return errors
