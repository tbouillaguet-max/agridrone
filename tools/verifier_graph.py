#!/usr/bin/env python3
"""Vérifie la cohérence de GRAPH.md avec les dossiers et les README des modules.

Contrôles :
  1. chaque ligne du tableau « Modules » a un dossier src/modules/<id>/ (sauf état « planifié ») ;
  2. chaque dossier de src/modules/ a une ligne dans le tableau ;
  3. chaque module actif a un README.md avec les 5 sections du template ;
  4. les identifiants du bloc Mermaid sont exactement ceux du tableau ;
  5. chaque module cité dans « Consomme » / « Fournit à » existe dans le tableau.

Usage : python tools/verifier_graph.py        (code de sortie 0 = tout est cohérent)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
MODULES = RACINE / "src" / "modules"
SECTIONS = ("## 1. Rôle", "## 2. Interfaces", "## 3. Dépendances", "## 4. Commandes", "## 5. Règle d'Isolation")


def lire_tableau(texte: str) -> dict[str, dict[str, str]]:
    bloc = texte.split("## Modules", 1)[1].split("\n## ", 1)[0]
    modules: dict[str, dict[str, str]] = {}
    for ligne in bloc.splitlines():
        if not ligne.startswith("|") or ligne.startswith("|---") or "Module (dossier" in ligne:
            continue
        cases = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if len(cases) < 6:
            continue
        m = re.search(r"`([a-z0-9-]+)`", cases[0])
        if m:
            modules[m.group(1)] = {"consomme": cases[3], "fournit": cases[4], "etat": cases[5]}
    return modules


def ids_mermaid(texte: str) -> set[str]:
    m = re.search(r"```mermaid\n(.*?)```", texte, re.S)
    if not m:
        return set()
    ids: set[str] = set()
    for ligne in m.group(1).splitlines()[1:]:
        ligne = re.sub(r'\|"[^"]*"\|', " ", ligne)
        ids.update(re.findall(r"[a-z][a-z0-9-]*", re.sub(r"-\.->|-->|---", " ", ligne)))
    return ids


def main() -> int:
    texte = (RACINE / "GRAPH.md").read_text(encoding="utf-8")
    tableau = lire_tableau(texte)
    erreurs: list[str] = []
    dossiers = {d.name for d in MODULES.iterdir() if d.is_dir()} if MODULES.exists() else set()

    for mid, info in tableau.items():
        planifie = "planifié" in info["etat"]
        if not planifie and mid not in dossiers:
            erreurs.append(f"{mid} : dans le tableau mais sans dossier src/modules/{mid}/")
        if planifie and mid in dossiers:
            erreurs.append(f"{mid} : marqué « planifié » mais le dossier existe (mettre l'état à jour)")
        if not planifie and mid in dossiers:
            readme = MODULES / mid / "README.md"
            if not readme.exists():
                erreurs.append(f"{mid} : README.md absent")
            else:
                contenu = readme.read_text(encoding="utf-8")
                for s in SECTIONS:
                    if s not in contenu:
                        erreurs.append(f"{mid} : README.md sans la section « {s} »")
        for cle in ("consomme", "fournit"):
            for cite in re.findall(r"`([a-z0-9-]+)`", info[cle]):
                if cite not in tableau:
                    erreurs.append(f"{mid} : « {cite} » ({cle}) absent du tableau")
    for d in sorted(dossiers - set(tableau)):
        erreurs.append(f"{d} : dossier sans ligne dans GRAPH.md")

    mm = ids_mermaid(texte)
    for mid in sorted(set(tableau) - mm):
        erreurs.append(f"{mid} : absent du bloc Mermaid")
    for mid in sorted(mm - set(tableau)):
        erreurs.append(f"{mid} : dans le bloc Mermaid mais absent du tableau")

    if erreurs:
        print("GRAPH.md incohérent :")
        for e in erreurs:
            print(" -", e)
        return 1
    print(f"OK : {len(tableau)} modules, GRAPH.md cohérent avec les dossiers, les README et Mermaid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
