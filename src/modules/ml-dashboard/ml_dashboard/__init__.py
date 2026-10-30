"""ml_dashboard — standard de run, journalisation et dashboard des entraînements.

Le standard est décrit dans STANDARD.md (à la racine du dépôt).
"""

from .standard import SCHEMA_VERSION
from .validate import ValidationReport, find_runs, validate_run

__version__ = "0.1.0"
__all__ = ["SCHEMA_VERSION", "ValidationReport", "find_runs", "validate_run", "__version__"]
