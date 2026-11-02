"""Tests de l'archivage de serveur_local.py (bibliothèque standard).

    python -m unittest discover -s planificateur/tests -p "test_*.py"
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serveur_local as s  # noqa: E402


def mission(id_mission=12, culture="ble", **autres):
    m = {"version": 1, "nom": "essai", "idMission": id_mission, "culture": culture, "limites": [[48.0, 1.0]] * 3,
         "zones": [], "waypoints": [], "modifieLe": "2026-10-29T10:00:00Z"}
    m.update(autres)
    return json.dumps(m).encode("utf-8")


class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dossier = Path(self.tmp.name) / "missions"
        self.archive = s.Archive(self.dossier)

    def tearDown(self):
        self.tmp.cleanup()

    def test_archivage_puis_suffixe_pour_une_autre_mission(self):
        r = self.archive.archiver("12", mission())
        self.assertEqual(Path(r["chemin"]).name, "mission_12.json")
        self.assertFalse(r["suffixe"])
        lu = json.loads((self.dossier / "mission_12.json").read_text(encoding="utf-8"))
        self.assertEqual(lu["culture"], "ble")
        # Même mission renvoyée (seul modifieLe change) : pas de doublon
        r = self.archive.archiver("12", mission(modifieLe="2026-10-29T11:00:00Z"))
        self.assertEqual(Path(r["chemin"]).name, "mission_12.json")
        # Autre mission avec le même identifiant : suffixe, jamais d'écrasement
        r = self.archive.archiver("12", mission(culture="mais"))
        self.assertEqual(Path(r["chemin"]).name, "mission_12_2.json")
        self.assertTrue(r["suffixe"])
        r = self.archive.archiver("12", mission(culture="pommier"))
        self.assertEqual(Path(r["chemin"]).name, "mission_12_3.json")
        self.assertEqual(json.loads((self.dossier / "mission_12.json").read_text(encoding="utf-8"))["culture"], "ble")

    def test_refus_explicites(self):
        cas = [("12", b"pas du json", "JSON"), ("0", mission(), "identifiant"), ("abc", mission(), "identifiant"),
               ("13", mission(12), "différent"), ("12", mission(culture=None), "culture"),
               ("12", mission(culture="vigne"), "culture"), ("12", mission(version=2), "version")]
        for id_texte, corps, motif in cas:
            with self.subTest(motif=motif, id=id_texte):
                with self.assertRaises(s.ErreurArchive) as ctx:
                    self.archive.archiver(id_texte, corps)
                self.assertIn(motif, str(ctx.exception))
        self.assertFalse(list(self.dossier.glob("*.json")) if self.dossier.exists() else [])

    def test_dossier_parent_absent(self):
        archive = s.Archive(Path(self.tmp.name) / "absent" / "missions")
        with self.assertRaises(s.ErreurArchive) as ctx:
            archive.archiver("12", mission())
        self.assertIn("--missions", str(ctx.exception))

    def test_identifiant_libre(self):
        self.assertEqual(self.archive.id_libre("12"), {"id": 12})
        self.archive.archiver("12", mission())
        self.archive.archiver("13", mission(13))
        self.assertEqual(self.archive.id_libre("12"), {"id": 14})
        self.archive.archiver("65535", mission(65535))
        self.assertEqual(self.archive.id_libre("65535"), {"id": 1})

    def test_journal(self):
        self.archive.journaliser(json.dumps({"niveau": "erreur", "texte": "pas de réponse\nd'AU2", "idMission": 7}).encode())
        lignes = (self.dossier / "journal_planificateur.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lignes), 1)
        horodatage, niveau, mission_, texte = lignes[0].split("\t")
        self.assertRegex(horodatage, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual((niveau, mission_, texte), ("ERREUR", "mission 7", "pas de réponse d'AU2"))


class ServeurTest(unittest.TestCase):
    """Aller-retour HTTP réel, comme depuis la page."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        s.Gestionnaire.archive = s.Archive(Path(cls.tmp.name) / "missions")
        cls.serveur = ThreadingHTTPServer(("127.0.0.1", 0), s.Gestionnaire)
        cls.base = f"http://127.0.0.1:{cls.serveur.server_address[1]}"
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.serveur.shutdown()
        cls.serveur.server_close()
        cls.tmp.cleanup()

    def post(self, chemin, corps):
        req = urllib.request.Request(self.base + chemin, data=corps, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_api(self):
        code, r = self.post("/api/missions?id=40", mission(40))
        self.assertEqual(code, 200)
        self.assertTrue(r["chemin"].endswith("mission_40.json"))
        code, r = self.post("/api/missions?id=41", mission(41, culture=None))
        self.assertEqual(code, 400)
        self.assertIn("culture", r["erreur"])
        with urllib.request.urlopen(self.base + "/api/missions/libre?depuis=40") as rep:
            self.assertEqual(json.loads(rep.read()), {"id": 41})
        code, _ = self.post("/api/journal", json.dumps({"niveau": "avertissement", "texte": "essai"}).encode())
        self.assertEqual(code, 200)
        code, _ = self.post("/api/inconnue", b"{}")
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
