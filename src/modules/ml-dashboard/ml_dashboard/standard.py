"""Constantes et conventions du standard de run ``ml_dashboard``.

Ce module est la *seule* source de vérité côté code pour les noms de fichiers,
les valeurs autorisées et les conventions de nommage. Le validateur, le
RunLogger, les adaptateurs et le dashboard l'importent tous : changer une
convention ici impose d'incrémenter ``SCHEMA_VERSION`` (voir STANDARD.md).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Final

# --------------------------------------------------------------------------- #
# Version du standard
# --------------------------------------------------------------------------- #
SCHEMA_VERSION: Final[int] = 1
"""Version écrite par ce code dans tous les fichiers JSON du run."""

SUPPORTED_SCHEMA_VERSIONS: Final[tuple[int, ...]] = (1,)
"""Versions que ce code sait lire. Une version plus récente est refusée."""

# --------------------------------------------------------------------------- #
# Valeurs énumérées
# --------------------------------------------------------------------------- #
TASKS: Final[tuple[str, ...]] = ("classification", "detection", "segmentation")
DETECTION_TASKS: Final[tuple[str, ...]] = ("detection", "segmentation")
STATUSES: Final[tuple[str, ...]] = ("running", "completed", "failed", "interrupted")
SPLITS: Final[tuple[str, ...]] = ("val", "test")
ARTIFACT_KINDS: Final[tuple[str, ...]] = ("image", "html")
LABEL_MODES: Final[tuple[str, ...]] = ("single", "multi")
"""single : une image = une classe (probas qui somment à 1).
multi : une image = 0..n classes (une proba indépendante par classe)."""

MULTI_LABEL_SEPARATOR: Final[str] = "|"
"""Séparateur des classes dans y_true / y_pred en mode multi (ex. ``mildiou|carence_eau``)."""

DEFAULT_MULTI_LABEL_THRESHOLD: Final[float] = 0.5

# --------------------------------------------------------------------------- #
# Noms de fichiers et dossiers
# --------------------------------------------------------------------------- #
META_FILE: Final[str] = "meta.json"
CONFIG_FILE: Final[str] = "config.yaml"
CLASSES_FILE: Final[str] = "classes.json"
EPOCHS_FILE: Final[str] = "epochs.csv"
PREDICTIONS_DIR: Final[str] = "predictions"
DETECTION_DIR: Final[str] = "detection"
DETECTION_METRICS_FILE: Final[str] = "metrics.json"
DETECTION_PR_FILE: Final[str] = "pr_curves.csv"
DETECTION_EXAMPLES_DIR: Final[str] = "examples"
ARTIFACTS_DIR: Final[str] = "artifacts"
EXTRA_RESULTS_DIR: Final[str] = "extra_results"
MODEL_DIR: Final[str] = "model"
MANIFEST_FILE: Final[str] = "manifest.json"

TOP_LEVEL_ENTRIES: Final[frozenset[str]] = frozenset(
    {
        META_FILE,
        CONFIG_FILE,
        CLASSES_FILE,
        EPOCHS_FILE,
        PREDICTIONS_DIR,
        DETECTION_DIR,
        ARTIFACTS_DIR,
        EXTRA_RESULTS_DIR,
        MODEL_DIR,
    }
)

IMAGE_EXTENSIONS: Final[frozenset[str]] = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})
HTML_EXTENSIONS: Final[frozenset[str]] = frozenset({".html", ".htm"})

# --------------------------------------------------------------------------- #
# epochs.csv
# --------------------------------------------------------------------------- #
EPOCHS_REQUIRED_COLUMNS: Final[tuple[str, ...]] = ("epoch", "lr", "train_loss", "val_loss")

EPOCH_METRIC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(train|val)_[a-z0-9]+(?:_[a-z0-9]+)*(?:__[^,\n\r]+)?$"
)
"""Colonne libre : ``train_<metrique>`` ou ``val_<metrique>``, en minuscules,
suivie optionnellement de ``__<classe>`` pour une métrique par classe
(ex. ``val_recall__mildiou``)."""

PER_CLASS_SEPARATOR: Final[str] = "__"

# --------------------------------------------------------------------------- #
# predictions/<split>.csv
# --------------------------------------------------------------------------- #
PREDICTION_REQUIRED_COLUMNS: Final[tuple[str, ...]] = ("id", "group", "y_true", "y_pred", "image_path")
PROBA_PREFIX: Final[str] = "proba_"
PROBA_SUM_TOLERANCE: Final[float] = 1e-3

# --------------------------------------------------------------------------- #
# Identifiants
# --------------------------------------------------------------------------- #
SLUG_PATTERN: Final[str] = r"^[a-z0-9][a-z0-9_-]{0,63}$"
RUN_ID_PATTERN: Final[str] = r"^\d{8}_\d{6}_[a-z0-9][a-z0-9_-]{0,63}$"
CLASS_NAME_PATTERN: Final[str] = r"^[^\s,|\n\r](?:[^,|\n\r]*[^\s,|\n\r])?$"
"""Nom de classe : ni virgule, ni ``|``, ni retour à la ligne, pas d'espace
en début ou fin (les espaces internes sont permis)."""

_SLUG_CLEAN = re.compile(r"[^a-z0-9_-]+")


def slugify(text: str) -> str:
    """Transforme un texte libre en identifiant conforme à ``SLUG_PATTERN``.

    >>> slugify("EfficientNet B0 / 224px")
    'efficientnet-b0-224px'
    """
    slug = _SLUG_CLEAN.sub("-", text.strip().lower()).strip("-_")
    if not slug:
        raise ValueError(f"Impossible de dériver un identifiant de {text!r}")
    return slug[:64]


def make_run_id(short_name: str, when: datetime | None = None) -> str:
    """Construit un ``run_id`` au format ``AAAAMMJJ_HHMMSS_nomcourt``.

    >>> make_run_id("EffNet B0", datetime(2026, 10, 29, 18, 5, 0))
    '20261029_180500_effnet-b0'
    """
    when = when or datetime.now()
    return f"{when:%Y%m%d_%H%M%S}_{slugify(short_name)}"


def proba_column(class_name: str) -> str:
    """Nom de la colonne de probabilité d'une classe dans predictions/*.csv."""
    return f"{PROBA_PREFIX}{class_name}"


def split_labels(cell: str) -> list[str]:
    """Décode une cellule y_true / y_pred multi-label (``""`` = aucune classe)."""
    cell = cell.strip()
    return [c for c in cell.split(MULTI_LABEL_SEPARATOR)] if cell else []


def join_labels(labels: list[str]) -> str:
    """Encode une liste de classes pour une cellule multi-label."""
    return MULTI_LABEL_SEPARATOR.join(labels)


def per_class_column(split: str, metric: str, class_name: str) -> str:
    """Nom d'une métrique par classe dans epochs.csv (ex. ``val_recall__mildiou``)."""
    if split not in ("train", "val"):
        raise ValueError(f"split doit valoir 'train' ou 'val', reçu {split!r}")
    return f"{split}_{metric}{PER_CLASS_SEPARATOR}{class_name}"


def split_metric_column(column: str) -> tuple[str, str, str | None]:
    """Décompose une colonne libre d'epochs.csv en (split, métrique, classe|None).

    >>> split_metric_column("val_recall__mildiou")
    ('val', 'recall', 'mildiou')
    >>> split_metric_column("train_acc")
    ('train', 'acc', None)
    """
    if not EPOCH_METRIC_PATTERN.match(column):
        raise ValueError(f"Colonne non conforme : {column!r}")
    split, rest = column.split("_", 1)
    metric, sep, cls = rest.partition(PER_CLASS_SEPARATOR)
    return split, metric, (cls if sep else None)
