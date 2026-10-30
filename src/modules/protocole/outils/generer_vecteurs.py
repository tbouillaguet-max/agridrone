#!/usr/bin/env python3
"""Génère les vecteurs de test partagés du protocole commun.

Ce script est volontairement INDÉPENDANT des implémentations du dépôt : il
encode les trames directement avec `struct` en suivant SPECIFICATION.md.
Les implémentations JavaScript et C++ sont ensuite testées contre
son résultat (si elles se trompent toutes de la même façon que ce script,
c'est la spécification qu'il faut relire).

Usage :  python3 protocole/outils/generer_vecteurs.py
Écrit :  protocole/vecteurs_test.json
         protocole/arduino/test_hote/vecteurs_test.h
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]


def crc16(donnees: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE : poly 0x1021, init 0xFFFF, sans réflexion."""
    for octet in donnees:
        crc ^= octet << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def trame(type_: int, sequence: int, donnees: bytes) -> bytes:
    corps = struct.pack("<BBHB", 1, type_, sequence, len(donnees)) + donnees
    return b"\xAA\x55" + corps + struct.pack("<H", crc16(corps))


def polygone(sommets: list[list[int]]) -> bytes:
    return b"".join(struct.pack("<ii", lat, lon) for lat, lon in sommets)


LAT = 488566100  # 48,85661° N
LON = 23522200   # 2,35222° E

# (nom, type, séquence, format struct, champs ordonnés) — messages à taille fixe
VECTEURS_FIXES = [
    ("heartbeat_au1", 0x01, 1, "<BBI", {"emetteur": 5, "etat": 0x03, "temps_ms": 123456}),
    ("heartbeat_au2", 0x01, 2, "<BBI", {"emetteur": 0, "etat": 0x4D, "temps_ms": 987654}),
    ("ack_arret_urgence", 0x02, 300, "<BH", {"type_acquitte": 0x24, "sequence_acquittee": 17}),
    ("nack_etat", 0x03, 301, "<BHB", {"type_refuse": 0x40, "sequence_refusee": 18, "code": 3}),
    ("telemetrie", 0x10, 42, "<IhhHiiiiHhHHhBBBBHBHH", {
        "temps_ms": 987654, "roulis_cdeg": -1234, "tangage_cdeg": 567, "lacet_cdeg": 35999,
        "latitude_e7": LAT, "longitude_e7": LON, "altitude_msl_cm": 3550, "altitude_relative_cm": 1200,
        "vitesse_sol_cms": 350, "vitesse_verticale_cms": -25, "route_cdeg": 9000,
        "tension_batterie_mv": 15200, "courant_batterie_ca": 1250, "batterie_pct": 76,
        "mode_vol": 4, "etat_gps": 3, "nb_satellites": 14, "hdop_x100": 85, "drapeaux": 0x4F,
        "waypoint_courant": 3, "photos_declenchees": 27}),
    ("alerte_perte_au2", 0x11, 43, "<BBBBhB", {
        "code": 0x0E, "gravite": 3, "source": 5, "action": 3, "valeur": 0, "actif": 1}),
    ("commande_mode", 0x20, 65535, "<B", {"mode_vol": 4}),
    ("commande_manuelle", 0x21, 12, "<hhhh", {"roulis": -1000, "tangage": 500, "lacet": 0, "gaz": 1000}),
    ("atterrissage", 0x22, 5, "<", {}),
    ("retour_maison", 0x23, 6, "<", {}),
    ("arret_urgence", 0x24, 7, "<H", {"cle": 0x5AA5}),
    ("mission_ack", 0x45, 77, "<HBHB", {"id_mission": 12, "element": 3, "index": 2, "statut": 0}),
    ("mission_verification", 0x46, 78, "<HBH", {"id_mission": 12, "element": 3, "index": 2}),
]

# Une mission complète (sert aussi au calcul du CRC de mission)
LIMITES = [[488560000, 23510000], [488560000, 23530000], [488575000, 23530000], [488575000, 23510000]]
ZONE0 = [[488565000, 23518000], [488567000, 23518000], [488566000, 23521000]]
WAYPOINTS = [
    (488561000, 23512000, 500, 250, 1),
    (488561000, 23528000, 500, 250, 2),
    (488563000, 23528000, 500, 250, 1),
    (488563000, 23512000, 500, 250, 2),
]


def main() -> None:
    resultat: dict = {
        "description": "Vecteurs de test du protocole commun v1 (générés par "
                       "protocole/outils/generer_vecteurs.py). Ne pas modifier à la main.",
        "crc": [{"ascii": "123456789", "crc": 0x29B1}, {"ascii": "", "crc": 0xFFFF}],
        "trames": [],
    }

    def ajouter(nom: str, type_: int, seq: int, champs: dict, donnees: bytes) -> bytes:
        t = trame(type_, seq, donnees)
        resultat["trames"].append({"nom": nom, "type": type_, "sequence": seq, "champs": champs,
                                   "donnees_hex": donnees.hex(), "hex": t.hex()})
        return t

    par_nom: dict[str, bytes] = {}
    for nom, type_, seq, fmt, champs in VECTEURS_FIXES:
        par_nom[nom] = ajouter(nom, type_, seq, champs, struct.pack(fmt, *champs.values()))

    # --- Charges utiles variables -------------------------------------------
    texte = "Mission validée, prête à voler"
    ajouter("texte_utf8", 0x04, 2, {"gravite": 1, "source": 0, "texte": texte},
            struct.pack("<BB", 1, 0) + texte.encode("utf-8"))

    distances = [120, 0xFFFF, 340]
    ajouter("distances_tourelle", 0x12, 45,
            {"angle_debut_cdeg": -4500, "pas_cdeg": 4500, "distances_cm": distances},
            struct.pack("<Bhh", len(distances), -4500, 4500) + struct.pack("<3H", *distances))

    # --- Mission complète ------------------------------------------------------
    id_mission = 12
    debut = struct.pack("<HHBBHHBB", id_mission, len(WAYPOINTS), len(LIMITES), 1, 180, 250, 1, 30)
    ajouter("mission_debut", 0x40, 7, {
        "id_mission": id_mission, "nb_waypoints": len(WAYPOINTS), "nb_sommets_limites": len(LIMITES),
        "nb_zones": 1, "distance_photos_cm": 180, "vitesse_cms": 250, "options": 1, "hauteur_max_m": 30,
    }, debut)

    limites = struct.pack("<HB", id_mission, len(LIMITES)) + polygone(LIMITES)
    ajouter("mission_limites", 0x41, 8, {"id_mission": id_mission, "sommets": LIMITES}, limites)

    zone = struct.pack("<HBB", id_mission, 0, len(ZONE0)) + polygone(ZONE0)
    ajouter("zone_interdite", 0x42, 9, {"id_mission": id_mission, "index_zone": 0, "sommets": ZONE0}, zone)

    waypoints = []
    for i, (lat, lon, alt, vit, action) in enumerate(WAYPOINTS):
        d = struct.pack("<HHiiiHB", id_mission, i, lat, lon, alt, vit, action)
        waypoints.append(d)
        ajouter(f"mission_waypoint_{i}", 0x43, 10 + i, {
            "id_mission": id_mission, "index": i, "latitude_e7": lat, "longitude_e7": lon,
            "altitude_relative_cm": alt, "vitesse_cms": vit, "action": action}, d)

    crc_mission = 0xFFFF
    for d in [debut, limites, zone, *waypoints]:
        crc_mission = crc16(d, crc_mission)
    fin = struct.pack("<HH", id_mission, crc_mission)
    ajouter("mission_fin", 0x44, 14, {"id_mission": id_mission, "crc_mission": crc_mission}, fin)

    resultat["mission"] = {
        "debut_hex": debut.hex(),
        "limites_hex": limites.hex(),
        "zones_hex": [zone.hex()],
        "waypoints_hex": [w.hex() for w in waypoints],
        "crc": crc_mission,
    }

    # --- Flux série avec bruit et une trame corrompue ------------------------
    a = par_nom["heartbeat_au1"]
    b = bytearray(par_nom["telemetrie"])
    b[12] ^= 0x40  # un bit inversé dans les données ⇒ CRC faux
    c = par_nom["ack_arret_urgence"]
    flux = bytes([0x00, 0x13, 0xAA, 0x01]) + a + bytes(b) + bytes([0xAA]) + c
    resultat["flux"] = {"hex": flux.hex(), "trames_attendues": [a.hex(), c.hex()], "erreurs_crc": 1}

    chemin_json = RACINE / "vecteurs_test.json"
    chemin_json.write_text(json.dumps(resultat, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"écrit : {chemin_json}")

    # --- En-tête C++ pour le test sur PC de ProtocoleDrone.h ------------------
    lignes = [
        "// Généré par protocole/outils/generer_vecteurs.py — ne pas modifier à la main.",
        "#pragma once",
        "#include <stdint.h>",
        "",
        "struct VecteurTrame { const char *nom; const char *hex; };",
        "static const VecteurTrame VECTEURS_TRAMES[] = {",
        *[f'  {{"{v["nom"]}", "{v["hex"]}"}},' for v in resultat["trames"]],
        "};",
        f"static const unsigned NB_VECTEURS_TRAMES = {len(resultat['trames'])};",
        f'static const char *FLUX_HEX = "{flux.hex()}";',
        f"static const uint16_t CRC_MISSION_ATTENDU = 0x{crc_mission:04X};",
        "",
    ]
    chemin_h = RACINE / "arduino" / "test_hote" / "vecteurs_test.h"
    chemin_h.parent.mkdir(parents=True, exist_ok=True)
    chemin_h.write_text("\n".join(lignes), encoding="utf-8")
    print(f"écrit : {chemin_h}")


if __name__ == "__main__":
    main()
