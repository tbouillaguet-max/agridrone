"""Permet ``python -m ml_dashboard ...``."""

import sys

from .cli import main

if __name__ == "__main__":  # garde : évite l'exécution lors d'un simple import
    sys.exit(main())
