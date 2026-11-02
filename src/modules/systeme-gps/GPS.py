"""Étape 2 — Écoute brute du GPS du Phantom 3 à travers le pont USB de l'Uno.

Montage (ATmega328P neutralisé, l'Uno sert de simple adaptateur USB-série) :
    RESET Uno -> GND Uno         (fil direct : le 328P reste en reset)
    3.3V Uno  -> fil rouge GPS   (+3,3 V)
    GND Uno   -> fil noir GPS
    D1 (TX)   -> fil jaune GPS   (TX du GPS ; oui, TX sur "TX" : la broche
                                  D1 arrive sur l'entrée du convertisseur USB)
    fil marron (RX GPS) et orange (impulsion 5 Hz) : NON branchés.
Aucune ligne 5 V ne va donc vers le GPS.

Usage :
    python sniff_gps.py COM5              # essaie chaque vitesse, puis bilan
    python sniff_gps.py COM5 --baud 9600  # flux continu à une vitesse donnée
    (sous Linux : /dev/ttyACM0, sous macOS : /dev/cu.usbmodem...)

À observer : une vitesse avec des phrases NMEA valides ($GPGGA, $GNRMC...)
ou des trames UBX (B5 62) valides. Si tout est illisible à toutes les
vitesses, le protocole est probablement propriétaire DJI.
"""

import argparse
import re
import sys
import time

import serial

VITESSES = [4800, 9600, 19200, 38400, 57600, 115200, 230400]

NMEA = re.compile(rb"\$([A-Z]{5}[^*\r\n$]{0,80})\*([0-9A-Fa-f]{2})")


def compter_nmea(data):
    """Renvoie (phrases valides, types vus)."""
    valides, types = 0, set()
    for m in NMEA.finditer(data):
        somme = 0
        for b in m.group(1):
            somme ^= b
        if somme == int(m.group(2), 16):
            valides += 1
            types.add(m.group(1)[:5].decode())
    return valides, types


def compter_ubx(data):
    """Compte les trames UBX (B5 62 ...) dont la somme de contrôle est juste."""
    valides, i = 0, 0
    while True:
        i = data.find(b"\xb5\x62", i)
        if i < 0 or i + 8 > len(data):
            return valides
        longueur = data[i + 4] | (data[i + 5] << 8)
        fin = i + 6 + longueur + 2
        if fin <= len(data):
            ck_a = ck_b = 0
            for b in data[i + 2:i + 6 + longueur]:
                ck_a = (ck_a + b) & 0xFF
                ck_b = (ck_b + ck_a) & 0xFF
            if data[fin - 2] == ck_a and data[fin - 1] == ck_b:
                valides += 1
        i += 2


def part_ascii(data):
    if not data:
        return 0.0
    lisibles = sum(1 for b in data if 32 <= b < 127 or b in (10, 13))
    return lisibles / len(data)


def vidage(data, n=256):
    """Affiche n octets en hexadécimal + ASCII, 16 par ligne."""
    for off in range(0, min(len(data), n), 16):
        bloc = data[off:off + 16]
        hexa = " ".join(f"{b:02X}" for b in bloc)
        txt = "".join(chr(b) if 32 <= b < 127 else "." for b in bloc)
        print(f"  {off:04X}  {hexa:<47}  {txt}")


def ecouter(port, baud, duree):
    with serial.Serial(port, baud, timeout=0.2) as s:
        time.sleep(0.3)
        s.reset_input_buffer()
        data = bytearray()
        fin = time.time() + duree
        while time.time() < fin:
            data += s.read(4096)
    return bytes(data)


def balayage(port, duree):
    bilan = []
    for baud in VITESSES:
        print(f"\n--- {baud} bauds ({duree:.0f} s) ---")
        data = ecouter(port, baud, duree)
        n_nmea, types = compter_nmea(data)
        n_ubx = compter_ubx(data)
        n_dji = data.count(b"\x55\xaa")
        ascii_ = part_ascii(data)
        print(f"  {len(data)} octets reçus, {ascii_:.0%} ASCII lisible, "
              f"NMEA valides: {n_nmea}, UBX valides: {n_ubx}, "
              f"en-têtes 55 AA (style DJI): {n_dji}")
        if types:
            print("  types NMEA :", ", ".join(sorted(types)))
        vidage(data)
        bilan.append((baud, len(data), n_nmea, n_ubx, n_dji))

    print("\n=== BILAN ===")
    print(" vitesse  octets  NMEA  UBX  55AA")
    for baud, n, a, b, c in bilan:
        print(f"{baud:>8} {n:>7} {a:>5} {b:>4} {c:>5}")
    if all(n == 0 for _, n, *_ in bilan):
        print("Aucun octet : vérifier alimentation, GND, fil jaune sur D1, "
              "RESET bien relié à GND.")
        return
    meilleur = max(bilan, key=lambda x: (x[2] + x[3], x[1]))
    if meilleur[2] + meilleur[3] > 0:
        print(f"-> Protocole standard u-blox détecté à {meilleur[0]} bauds.")
    else:
        print("-> Ni NMEA ni UBX valides : protocole probablement propriétaire. "
              "Copie-moi la sortie complète.")


def flux(port, baud):
    print(f"Flux brut à {baud} bauds (Ctrl+C pour arrêter)")
    with serial.Serial(port, baud, timeout=0.5) as s:
        while True:
            ligne = s.readline()
            if ligne:
                print(ligne.decode("ascii", "replace").rstrip())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("port", help="port série de l'Uno (COM5, /dev/ttyACM0...)")
    p.add_argument("--baud", type=int, help="écouter en continu à cette vitesse")
    p.add_argument("--duree", type=float, default=4.0,
                   help="secondes d'écoute par vitesse (défaut 4)")
    args = p.parse_args()
    try:
        if args.baud:
            flux(args.port, args.baud)
        else:
            balayage(args.port, args.duree)
    except serial.SerialException as e:
        sys.exit(f"Erreur port série : {e}")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
