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
    python sniff_gps.py COM3              # essaie chaque vitesse, puis bilan
    python sniff_gps.py COM3 --baud 9600  # flux continu à une vitesse donnée
    python sniff_gps.py COM3 --baud 57600 --ubx  # liste et décode les messages UBX
    (sous Linux : /dev/ttyACM0, sous macOS : /dev/cu.usbmodem...)

À observer : une vitesse avec des phrases NMEA valides ($GPGGA, $GNRMC...)
ou des trames UBX (B5 62) valides. Si tout est illisible à toutes les
vitesses, le protocole est probablement propriétaire DJI.
"""

import argparse
import re
import struct
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


def trames_ubx(data):
    """Renvoie les trames UBX (B5 62 ...) valides : (classe, id, charge utile)."""
    trames, i = [], 0
    while True:
        i = data.find(b"\xb5\x62", i)
        if i < 0 or i + 8 > len(data):
            return trames
        longueur = data[i + 4] | (data[i + 5] << 8)
        fin = i + 6 + longueur + 2
        if fin <= len(data):
            ck_a = ck_b = 0
            for b in data[i + 2:i + 6 + longueur]:
                ck_a = (ck_a + b) & 0xFF
                ck_b = (ck_b + ck_a) & 0xFF
            if data[fin - 2] == ck_a and data[fin - 1] == ck_b:
                trames.append((data[i + 2], data[i + 3], data[i + 6:fin - 2]))
                i = fin
                continue
        i += 2


def compter_ubx(data):
    return len(trames_ubx(data))


NOMS_UBX = {
    (0x01, 0x01): "NAV-POSECEF", (0x01, 0x02): "NAV-POSLLH",
    (0x01, 0x03): "NAV-STATUS", (0x01, 0x04): "NAV-DOP",
    (0x01, 0x06): "NAV-SOL", (0x01, 0x07): "NAV-PVT",
    (0x01, 0x11): "NAV-VELECEF", (0x01, 0x12): "NAV-VELNED",
    (0x01, 0x20): "NAV-TIMEGPS", (0x01, 0x21): "NAV-TIMEUTC",
    (0x01, 0x30): "NAV-SVINFO", (0x01, 0x35): "NAV-SAT",
    (0x0A, 0x04): "MON-VER", (0x0A, 0x09): "MON-HW", (0x0D, 0x01): "TIM-TP",
}

FIX = {0: "aucun", 1: "estime", 2: "2D", 3: "3D", 4: "GNSS+estime", 5: "temps"}


def decoder_ubx(cls, mid, p):
    """Décode les messages de navigation utiles ; None si non géré."""
    u = lambda fmt, off: struct.unpack_from("<" + fmt, p, off)[0]
    try:
        if (cls, mid) == (0x01, 0x07):  # NAV-PVT
            return (f"{u('H', 4):04d}-{p[6]:02d}-{p[7]:02d} "
                    f"{p[8]:02d}:{p[9]:02d}:{p[10]:02d} UTC, fix {FIX.get(p[20], p[20])}, "
                    f"{p[23]} sat, lat {u('i', 28) / 1e7:.7f}, lon {u('i', 24) / 1e7:.7f}, "
                    f"alt {u('i', 36) / 1000:.1f} m, vitesse {u('i', 60) / 1000:.2f} m/s, "
                    f"pDOP {u('H', 76) / 100:.2f}")
        if (cls, mid) == (0x01, 0x06):  # NAV-SOL
            return (f"fix {FIX.get(p[10], p[10])}, {p[47]} sat, "
                    f"precision pos {u('I', 24) / 100:.1f} m, pDOP {u('H', 44) / 100:.2f}")
        if (cls, mid) == (0x01, 0x02):  # NAV-POSLLH
            return (f"lat {u('i', 8) / 1e7:.7f}, lon {u('i', 4) / 1e7:.7f}, "
                    f"alt {u('i', 16) / 1000:.1f} m, precision h {u('I', 20) / 1000:.1f} m")
        if (cls, mid) == (0x01, 0x03):  # NAV-STATUS
            return f"fix {FIX.get(p[4], p[4])}, flags {p[5]:#04x}"
        if (cls, mid) == (0x01, 0x04):  # NAV-DOP
            return f"pDOP {u('H', 6) / 100:.2f}, hDOP {u('H', 12) / 100:.2f}"
        if (cls, mid) == (0x01, 0x12):  # NAV-VELNED
            return (f"vitesse sol {u('I', 20) / 100:.2f} m/s, "
                    f"cap {u('i', 24) / 1e5:.1f} deg")
        if (cls, mid) == (0x01, 0x21):  # NAV-TIMEUTC
            return (f"{u('H', 12):04d}-{p[14]:02d}-{p[15]:02d} "
                    f"{p[16]:02d}:{p[17]:02d}:{p[18]:02d} UTC, valid {p[19]:#04x}")
    except (struct.error, IndexError):
        return "charge utile trop courte"
    return None


def analyser_ubx(port, baud, duree):
    print(f"Écoute UBX à {baud} bauds pendant {duree:.0f} s...")
    trames = trames_ubx(ecouter(port, baud, duree))
    if not trames:
        print("Aucune trame UBX valide.")
        return
    vus = {}
    for cls, mid, p in trames:
        vus.setdefault((cls, mid), []).append(p)
    print("\n classe id   nom          nb  taille  dernier contenu")
    for (cls, mid), lst in sorted(vus.items()):
        nom = NOMS_UBX.get((cls, mid), "?")
        print(f"   {cls:02X}   {mid:02X}  {nom:<12} {len(lst):>3} {len(lst[-1]):>6}")
        texte = decoder_ubx(cls, mid, lst[-1])
        if texte:
            print(f"        -> {texte}")
        else:
            print("        -> " + " ".join(f"{b:02X}" for b in lst[-1][:32])
                  + (" ..." if len(lst[-1]) > 32 else ""))


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
        if b"Etape" in data:
            print("  !!! Texte d'un sketch Arduino : le 328P tourne, RESET n'est "
                  "PAS relié à GND. Débrancher l'USB tout de suite.")
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
    p.add_argument("port", help="port série de l'Uno (COM3, /dev/ttyACM0...)")
    p.add_argument("--baud", type=int, help="écouter en continu à cette vitesse")
    p.add_argument("--ubx", action="store_true",
                   help="lister et décoder les messages UBX (avec --baud)")
    p.add_argument("--duree", type=float, default=4.0,
                   help="secondes d'écoute par vitesse (défaut 4)")
    args = p.parse_args()
    try:
        if args.baud and args.ubx:
            analyser_ubx(args.port, args.baud, max(args.duree, 10.0))
        elif args.baud:
            flux(args.port, args.baud)
        else:
            balayage(args.port, args.duree)
    except serial.SerialException as e:
        sys.exit(f"Erreur port série : {e}")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
