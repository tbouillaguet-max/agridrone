#!/usr/bin/env python3
"""Pipeline d'analyse des images du drone agricole (v1, lancement manuel).

Usage :
    python pipeline.py DOSSIER_DU_VOL [options]

    DOSSIER_DU_VOL   dossier déposé après le vol : images\\, photos.csv, boite_noire.csv
                     (en général drone\\vols\\entrant\\mission_00012_01)

Options :
    --missions DIR      missions archivées par le planificateur   (défaut : drone\\missions)
    --modeles FICHIER   registre des modèles                       (défaut : pipeline\\modeles.json)
    --sortie DIR        dossier des résultats                      (défaut : drone\\vols)
    --mission FICHIER   impose le fichier de mission (si plusieurs candidats)
    --nb-top N          nombre d'images malades les plus sûres dans le rapport (défaut 10)
    --nb-incertaines N  nombre d'images les moins sûres à vérifier       (défaut 10)
    --localisation M    auto (défaut : v2 si la mission donne la caméra, sinon v1), v1 ou v2
    --verifier          contrôle seulement les entrées, sans rien analyser ni écrire
    --silencieux        n'affiche que le résultat final

Codes de sortie : 0 = terminé ; 1 = entrées non conformes ou configuration incomplète
(le message nomme le fichier, la ligne et le module fautif) ; 2 = erreur inattendue.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

ICI = Path(__file__).resolve().parent
# Racine des données du monorepo : variable DRONE_DATA_DIR, sinon <racine du dépôt>/data
# (ICI = <racine>/src/modules/pipeline-analyse).
RACINE = Path(os.environ.get("DRONE_DATA_DIR") or ICI.parents[2] / "data")
sys.path.insert(0, str(ICI))

from analyse import ErreurPipeline, Options, VERSION_PIPELINE, executer  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    for flux in (sys.stdout, sys.stderr):  # console Windows : jamais de plantage sur un accent
        try:
            flux.reconfigure(errors="replace")
        except AttributeError:
            pass
    a = argparse.ArgumentParser(prog="pipeline.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("dossier_vol", type=Path)
    a.add_argument("--missions", type=Path, default=RACINE / "missions")
    a.add_argument("--modeles", type=Path, default=ICI / "modeles.json")
    a.add_argument("--sortie", type=Path, default=RACINE / "vols")
    a.add_argument("--mission", type=Path, default=None)
    a.add_argument("--nb-top", type=int, default=10)
    a.add_argument("--nb-incertaines", type=int, default=10)
    a.add_argument("--localisation", default="auto", choices=["auto", "v1", "v2"])
    a.add_argument("--verifier", action="store_true")
    a.add_argument("--silencieux", action="store_true")
    a.add_argument("--version", action="version", version=f"pipeline {VERSION_PIPELINE}")
    args = a.parse_args(argv)

    opts = Options(dossier_vol=args.dossier_vol.resolve(), dossier_missions=args.missions.resolve(),
                   registre=args.modeles.resolve(), dossier_sortie=args.sortie.resolve(),
                   mission_forcee=args.mission.resolve() if args.mission else None,
                   nb_top=args.nb_top, nb_incertaines=args.nb_incertaines,
                   verifier_seulement=args.verifier, silencieux=args.silencieux,
                   localisation=args.localisation)
    try:
        bilan = executer(opts)
    except ErreurPipeline as e:
        print(e.format(), file=sys.stderr)
        return 1
    except Exception:
        traceback.print_exc()
        print("[ECHEC] erreur inattendue du pipeline [module fautif : pipeline]", file=sys.stderr)
        return 2
    if args.verifier:
        print("[OK] entrées conformes")
    else:
        print(f"[OK] {bilan.nb_malades} image(s) malade(s) sur {bilan.nb_images} — rapport : {bilan.rapport}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
