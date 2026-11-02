"""Convertit un notebook au format « # %% » (.py) en .ipynb, sans dépendance externe.
Usage : python scripts/build_notebook.py notebooks/01_preparation_donnees.py notebooks/01_preparation_donnees.ipynb
"""
import json
import sys


def convert(src, dst):
    text = open(src, encoding="utf-8").read()
    cells, cur = [], None
    for line in text.split("\n"):
        if line.startswith("# %%"):
            if cur is not None:
                cells.append(cur)
            cur = {"type": "markdown" if "[markdown]" in line else "code", "lines": []}
        elif cur is not None:
            cur["lines"].append(line)
    cells.append(cur)
    out = []
    for c in cells:
        lines = c["lines"]
        while lines and lines[-1] == "":
            lines.pop()
        while lines and lines[0] == "":
            lines.pop(0)
        if c["type"] == "markdown":
            lines = [l[2:] if l.startswith("# ") else (l[1:] if l.startswith("#") else l) for l in lines]
        src_lines = [l + "\n" for l in lines[:-1]] + ([lines[-1]] if lines else [])
        if c["type"] == "markdown":
            out.append({"cell_type": "markdown", "metadata": {}, "source": src_lines})
        else:
            out.append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": src_lines})
    nb = {"cells": out,
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 4}
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)
    print(f"{dst} : {len(out)} cellules")


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
