"""Données : téléchargement, conversion, découpage, tuilage, augmentations (chantier 2).

Conventions :
* ``data/raw/<source>/``       — archives et fichiers tels que téléchargés (jamais modifiés) ;
* ``data/interim/<source>/``   — extractions et conversions intermédiaires ;
* ``data/processed/<tâche>/``  — jeux prêts à l'entraînement (YOLO, dossiers par classe,
  tuiles multibandes + masques), avec leurs fichiers de découpage train/val/test.

Le découpage se fait par source / parcelle / date, jamais aléatoirement par image.
"""
