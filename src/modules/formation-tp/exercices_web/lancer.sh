#!/bin/sh
# Sert la racine du dépôt sur http://localhost:8001 et ouvre la page des exercices web.
cd "$(dirname "$0")/../.." || exit 1
exec python3 planificateur/serveur_local.py 8001 --racine . --page tp/exercices_web/ "$@"
