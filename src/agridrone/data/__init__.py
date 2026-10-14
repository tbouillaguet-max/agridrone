"""Données : téléchargement, conversion, découpage, tuilage, augmentations (chantier 2).

Conventions (``<projet>`` = ``ble`` ou ``olivier``, voir ``agridrone.core.paths``) :
* ``data/<projet>/raw/<source>/``       — archives et fichiers tels que téléchargés
  (jamais modifiés) ;
* ``data/<projet>/interim/<source>/``   — extractions et conversions intermédiaires ;
* ``data/<projet>/processed/<tâche>/``  — jeux prêts à l'entraînement (YOLO, dossiers
  par classe, tuiles multibandes + masques), avec leurs fichiers de découpage.

Le découpage se fait par source / parcelle / date, jamais aléatoirement par image.
"""
