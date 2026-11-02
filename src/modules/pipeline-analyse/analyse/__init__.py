"""Pipeline d'analyse des images du drone agricole (v1).

Point d'entrée : ``pipeline.py`` (à la racine du module) ou ``analyse.executer``.
Voir NOTICE.md pour les entrées, les sorties et le fonctionnement.
"""
from .contrat import VERSION_PIPELINE, ErreurPipeline
from .executer import executer, Options

__all__ = ["VERSION_PIPELINE", "ErreurPipeline", "executer", "Options"]
