#!/usr/bin/env python3
"""Sert le planificateur sur http://localhost:8000 et archive les missions envoyées.

Web Serial (câble USB vers AU2) n'est autorisé que sur une page https:// ou
http://localhost : ce petit serveur (bibliothèque standard de Python, rien à
installer) suffit. Il n'écoute que sur la machine elle-même (127.0.0.1) et
force les bons types MIME (sous Windows, le registre annonce parfois les .js
en text/plain, ce qui bloque les modules JavaScript).

Il écrit aussi, pour la page, dans le dossier des missions (entrée E3 du
pipeline d'analyse des images) :
  * mission_<idMission>.json : chaque mission chargée avec succès dans AU2.
    Si l'identifiant est déjà archivé avec une AUTRE mission, le fichier est
    nommé mission_<id>_2.json, _3… (jamais d'écrasement) ;
  * journal_planificateur.txt : chaque erreur et avertissement de la page.

Usage :  python serveur_local.py [port] [--sans-navigateur] [--racine DOSSIER] [--page CHEMIN]
                                 [--missions DOSSIER]
         puis Ctrl+C pour arrêter.
         --racine   : dossier servi (par défaut, celui du planificateur) ;
         --page     : page ouverte dans le navigateur (chemin relatif à la racine) ;
         --missions : dossier d'archive (par défaut : Bureau/drone/missions).
Exemple (exercices web du TP, depuis la racine du dépôt) :
         python planificateur/serveur_local.py 8001 --racine . --page tp/exercices_web/
"""
from __future__ import annotations

import http.server
import json
import os
import re
import sys
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

_NOMBRES = [a for a in sys.argv[1:] if a.isdigit()]
PORT = int(_NOMBRES[0]) if _NOMBRES else 8000  # premier argument numérique, sinon 8000

# Cultures admises : à garder identiques à config.js (CONFIG.cultures) et au
# registre des modèles du pipeline (pipeline\modeles.json).
CULTURES = {"ble", "mais", "pommier"}
TAILLE_MAX_CORPS = 2_000_000
# Racine des données du monorepo : variable DRONE_DATA_DIR, sinon <racine du dépôt>/data
# (ce fichier est dans <racine>/src/modules/planificateur/).
DOSSIER_MISSIONS_DEFAUT = Path(os.environ.get("DRONE_DATA_DIR") or Path(__file__).resolve().parents[3] / "data") / "missions"
VERROU = threading.Lock()


class ErreurArchive(Exception):
    """Erreur à renvoyer à la page (code HTTP, message)."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def _sans_horodatage(mission: dict) -> dict:
    return {k: v for k, v in mission.items() if k != "modifieLe"}


class Archive:
    """Écritures dans le dossier des missions (testable sans serveur)."""

    def __init__(self, dossier: Path):
        self.dossier = dossier

    def preparer(self) -> None:
        if not self.dossier.parent.is_dir():
            raise ErreurArchive(500, f"dossier introuvable : {self.dossier.parent} "
                                     "(lancez serveur_local.py avec --missions DOSSIER)")
        self.dossier.mkdir(exist_ok=True)

    def candidats(self, id_mission: int) -> list[Path]:
        motif = re.compile(rf"^mission_{id_mission}(_\d+)?\.json$")
        return sorted(p for p in self.dossier.glob(f"mission_{id_mission}*.json") if motif.match(p.name))

    def archiver(self, id_texte: str, corps: bytes) -> dict:
        if not re.fullmatch(r"\d{1,5}", id_texte or "") or not 1 <= int(id_texte) <= 0xFFFF:
            raise ErreurArchive(400, f"identifiant de mission invalide : {id_texte!r}")
        id_mission = int(id_texte)
        try:
            mission = json.loads(corps.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as e:
            raise ErreurArchive(400, f"mission illisible (JSON invalide : {e})") from e
        # Contrôle de cohérence avec le planificateur (règle du projet).
        if not isinstance(mission, dict) or mission.get("version") != 1:
            raise ErreurArchive(400, "fichier de mission invalide (version 1 attendue) [module fautif : planificateur]")
        if mission.get("idMission") != id_mission:
            raise ErreurArchive(400, f"idMission {mission.get('idMission')} différent de {id_mission} "
                                     "[module fautif : planificateur]")
        if mission.get("culture") not in CULTURES:
            raise ErreurArchive(400, f"culture {mission.get('culture')!r} absente ou inconnue "
                                     f"(attendu : {', '.join(sorted(CULTURES))}) [module fautif : planificateur]")
        for cle in ("limites", "zones", "waypoints"):
            if not isinstance(mission.get(cle), list):
                raise ErreurArchive(400, f"champ {cle} absent [module fautif : planificateur]")

        with VERROU:
            self.preparer()
            texte = json.dumps(mission, ensure_ascii=False, indent=2) + "\n"
            for existant in self.candidats(id_mission):
                try:
                    if _sans_horodatage(json.loads(existant.read_text(encoding="utf-8"))) == _sans_horodatage(mission):
                        existant.write_text(texte, encoding="utf-8")  # même mission renvoyée : mise à jour
                        return {"ok": True, "chemin": str(existant), "suffixe": existant.stem != f"mission_{id_mission}"}
                except (OSError, ValueError):
                    continue
            chemin = self.dossier / f"mission_{id_mission}.json"
            n = 2
            while chemin.exists():
                chemin = self.dossier / f"mission_{id_mission}_{n}.json"
                n += 1
            # Création exclusive : jamais d'écrasement d'une autre mission.
            with open(chemin, "x", encoding="utf-8") as f:
                f.write(texte)
            return {"ok": True, "chemin": str(chemin), "suffixe": n > 2}

    def id_libre(self, depuis_texte: str) -> dict:
        try:
            depuis = int(depuis_texte)
        except (TypeError, ValueError):
            depuis = 1
        depuis = min(max(depuis, 1), 0xFFFF)
        with VERROU:
            if not self.dossier.is_dir():
                return {"id": depuis}
            pris = set()
            for p in self.dossier.glob("mission_*.json"):
                m = re.match(r"^mission_(\d+)(_\d+)?\.json$", p.name)
                if m:
                    pris.add(int(m.group(1)))
        for i in range(0xFFFF):
            candidat = (depuis - 1 + i) % 0xFFFF + 1
            if candidat not in pris:
                return {"id": candidat}
        return {"id": depuis}

    def journaliser(self, corps: bytes) -> dict:
        try:
            e = json.loads(corps.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as err:
            raise ErreurArchive(400, f"ligne de journal illisible : {err}") from err
        propre = lambda v: re.sub(r"[\r\n\t]+", " ", str(v if v is not None else ""))[:500]  # noqa: E731
        maintenant = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ligne = "\t".join([maintenant, propre(e.get("niveau")).upper(),
                           f"mission {propre(e.get('idMission')) or '-'}", propre(e.get("texte"))]) + "\n"
        with VERROU:
            self.preparer()
            with open(self.dossier / "journal_planificateur.txt", "a", encoding="utf-8") as f:
                f.write(ligne)
        return {"ok": True}


class Gestionnaire(http.server.SimpleHTTPRequestHandler):
    archive: Archive = Archive(DOSSIER_MISSIONS_DEFAUT)

    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".mjs": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
    }

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")  # toujours la dernière version des fichiers
        super().end_headers()

    def repondre_json(self, code: int, objet: dict) -> None:
        corps = json.dumps(objet, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def lire_corps(self) -> bytes:
        taille = int(self.headers.get("Content-Length") or 0)
        if taille > TAILLE_MAX_CORPS:
            raise ErreurArchive(413, "requête trop volumineuse")
        return self.rfile.read(taille)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/api/missions/libre":
            self.repondre_json(200, self.archive.id_libre(parse_qs(url.query).get("depuis", ["1"])[0]))
            return
        super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/missions":
                resultat = self.archive.archiver(parse_qs(url.query).get("id", [""])[0], self.lire_corps())
                print(f"mission archivée : {resultat['chemin']}")
                self.repondre_json(200, resultat)
            elif url.path == "/api/journal":
                self.repondre_json(200, self.archive.journaliser(self.lire_corps()))
            else:
                self.repondre_json(404, {"erreur": "adresse inconnue"})
        except ErreurArchive as e:
            print(f"archivage refusé : {e}")
            self.repondre_json(e.code, {"erreur": str(e)})
        except OSError as e:
            print(f"erreur disque : {e}")
            self.repondre_json(500, {"erreur": f"erreur disque : {e}"})


def ouvrir_navigateur(url: str) -> None:
    for nom in ("chrome", "google-chrome", "chromium", "windows-default", None):
        try:
            webbrowser.get(nom).open(url)
            return
        except webbrowser.Error:
            continue


def option(nom: str, defaut: str) -> str:
    """Valeur qui suit `nom` sur la ligne de commande (ex. --racine DOSSIER)."""
    if nom in sys.argv and sys.argv.index(nom) + 1 < len(sys.argv):
        return sys.argv[sys.argv.index(nom) + 1]
    return defaut


if __name__ == "__main__":
    racine = os.path.abspath(option("--racine", os.path.dirname(os.path.abspath(__file__))))
    Gestionnaire.archive = Archive(Path(option("--missions", str(DOSSIER_MISSIONS_DEFAUT))).expanduser().resolve())
    os.chdir(racine)
    url = f"http://localhost:{PORT}/{option('--page', '').lstrip('/')}"
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Gestionnaire) as serveur:
        print(f"Pages servies sur {url}  (ouvrez cette adresse dans Chrome ; Ctrl+C pour arrêter)")
        print(f"Missions archivées dans : {Gestionnaire.archive.dossier}")
        if not Gestionnaire.archive.dossier.parent.is_dir():
            print("  ATTENTION : ce dossier n'existe pas ; l'archivage échouera (option --missions DOSSIER).")
        if "--sans-navigateur" not in sys.argv:
            threading.Timer(1.0, ouvrir_navigateur, args=(url,)).start()
        try:
            serveur.serve_forever()
        except KeyboardInterrupt:
            print("\narrêt")
