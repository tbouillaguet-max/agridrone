#!/bin/sh
# Sert le planificateur sur http://localhost:8000 et l'ouvre dans le navigateur.
cd "$(dirname "$0")" || exit 1
exec python3 serveur_local.py "$@"
