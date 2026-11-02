// Protocole commun (protocole/SPECIFICATION.md) en JavaScript.
// Module ES sans dépendance : utilisé par la page ET par les tests Node.

export const VERSION = 1;
export const TAILLE_ENTETE = 7;
export const TAILLE_MIN = 9;
export const SOMMETS_MAX_TRAME = 30;

export const TYPE = Object.freeze({
  HEARTBEAT: 0x01, ACK: 0x02, NACK: 0x03, TEXTE: 0x04,
  TELEMETRIE: 0x10, ALERTE_AVARIE: 0x11, DISTANCES_TOURELLE: 0x12,
  COMMANDE_MODE: 0x20, COMMANDE_MANUELLE: 0x21, ATTERRISSAGE: 0x22, RETOUR_MAISON: 0x23, ARRET_URGENCE: 0x24,
  MISSION_DEBUT: 0x40, MISSION_LIMITES: 0x41, ZONE_INTERDITE: 0x42, MISSION_WAYPOINT: 0x43,
  MISSION_FIN: 0x44, MISSION_ACK: 0x45, MISSION_VERIFICATION: 0x46,
  // 0x30, 0x31, 0x47 et 0x50 : retirés, réservés (SPECIFICATION.md § 5)
});

const NOMS = Object.fromEntries(Object.entries(TYPE).map(([n, v]) => [v, n]));
export function nomType(type) {
  return NOMS[type] ?? `INCONNU_0x${type.toString(16).padStart(2, "0")}`;
}

export const EMETTEUR = Object.freeze({ AU2: 0, UNO: 1, BOITIER_SOL: 3, PLANIFICATEUR: 4, AU1: 5 });
export const NOMS_EMETTEURS = { 0: "AU2", 1: "tourelle", 3: "boîtier sol", 4: "planificateur", 5: "AU1" };

/** Drapeaux du heartbeat d'AU2 (§ 7.3). */
export const DRAPEAU = Object.freeze({
  ARME: 1, EN_VOL: 2, DEPART_DEFINI: 4, MISSION_CHARGEE: 8, FAILSAFE: 16, EVITEMENT: 32, LORA_OK: 64, LIAISON_AU_OK: 128,
});

export const CLE_ARRET_URGENCE = 0x5aa5;

/** Noms des codes d'avarie (§ 7.4). */
export const NOMS_AVARIES = {
  0x02: "perte de la liaison LoRa", 0x03: "perte de la tourelle", 0x04: "batterie faible", 0x05: "batterie critique",
  0x06: "GPS perdu", 0x07: "sortie des limites ou zone interdite", 0x08: "obstacle", 0x09: "défaut IMU",
  0x0a: "défaut baromètre", 0x0b: "défaut boussole", 0x0c: "défaut moteur", 0x0d: "perte de la liaison avec AU1",
  0x0e: "perte de la liaison avec AU2", 0x0f: "défaut de la carte SD", 0x10: "défaut caméra",
  0x11: "arrêt d'urgence", 0x12: "erreurs de liaison", 0x13: "redémarrage",
};

export const ELEMENT = Object.freeze({ DEBUT: 0, LIMITES: 1, ZONE: 2, WAYPOINT: 3, FIN: 4 });
export const NOMS_ELEMENTS = ["en-tête", "limites", "zone interdite", "waypoint", "fin"];

export const ACTION = Object.freeze({ PASSAGE: 0, DEBUT_PHOTOS: 1, FIN_PHOTOS: 2, PHOTO_UNIQUE: 3 });
export const NOMS_ACTIONS = ["passage", "début photos", "fin photos", "photo unique"];

export const OPTION = Object.freeze({ RETOUR_MAISON: 1, ATTERRIR: 2 });

export const STATUT = Object.freeze({
  OK: 0, ID_INCONNU: 1, INDEX_INVALIDE: 2, CAPACITE_DEPASSEE: 3, CRC_INVALIDE: 4,
  ELEMENT_INVALIDE: 5, ETAT_INCOMPATIBLE: 6, INCOMPLETE: 7,
  // codes locaux (jamais transmis)
  NACK_RECU: 0xfd, RELECTURE_DIFFERENTE: 0xfe, PAS_DE_REPONSE: 0xff,
});
export const NOMS_STATUTS = {
  0: "OK", 1: "identifiant de mission inconnu", 2: "index invalide", 3: "capacité dépassée",
  4: "CRC de mission invalide", 5: "élément invalide",
  6: "drone armé ou en vol (attendre l'atterrissage et le désarmement)", 7: "mission incomplète",
  0xfd: "élément refusé (NACK)", 0xfe: "la relecture ne correspond pas à l'envoi", 0xff: "pas de réponse",
};

// ---------------------------------------------------------------------------
// CRC-16/CCITT-FALSE
// ---------------------------------------------------------------------------
export function crc16(octets, debut = 0, fin = octets.length, crc = 0xffff) {
  for (let i = debut; i < fin; i++) {
    crc ^= octets[i] << 8;
    for (let b = 0; b < 8; b++) {
      crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
    }
  }
  return crc;
}

export class ErreurProtocole extends Error {}

// ---------------------------------------------------------------------------
// Trame
// ---------------------------------------------------------------------------
export function encoderTrame(type, sequence, donnees = new Uint8Array(0)) {
  if (donnees.length > 255) throw new ErreurProtocole("données trop longues");
  const t = new Uint8Array(TAILLE_MIN + donnees.length);
  t[0] = 0xaa;
  t[1] = 0x55;
  t[2] = VERSION;
  t[3] = type;
  t[4] = sequence & 0xff;
  t[5] = (sequence >> 8) & 0xff;
  t[6] = donnees.length;
  t.set(donnees, TAILLE_ENTETE);
  const crc = crc16(t, 2, TAILLE_ENTETE + donnees.length);
  t[TAILLE_ENTETE + donnees.length] = crc & 0xff;
  t[TAILLE_ENTETE + donnees.length + 1] = crc >> 8;
  return t;
}

/** Décode une trame complète (tableau qui ne contient qu'elle). */
export function decoderTrame(octets) {
  if (octets.length < TAILLE_MIN) throw new ErreurProtocole("trame trop courte");
  if (octets[0] !== 0xaa || octets[1] !== 0x55) throw new ErreurProtocole("synchro absente");
  if (octets[2] !== VERSION) throw new ErreurProtocole(`version ${octets[2]} non supportée`);
  const longueur = octets[6];
  if (octets.length !== TAILLE_MIN + longueur) throw new ErreurProtocole("longueur incohérente");
  const fin = TAILLE_ENTETE + longueur;
  if (crc16(octets, 2, fin) !== (octets[fin] | (octets[fin + 1] << 8))) throw new ErreurProtocole("CRC invalide");
  return { type: octets[3], sequence: octets[4] | (octets[5] << 8), donnees: octets.slice(TAILLE_ENTETE, fin) };
}

/**
 * Décodeur de flux : la liaison série livre les octets par morceaux ; on pousse
 * les octets au fil de l'eau et il rend les trames complètes (§ 2.2).
 */
export class DecodeurTrames {
  constructor() {
    this.etat = 0; // 0 AA, 1 55, 2 version, 3 type, 4 seqL, 5 seqH, 6 longueur, 7 données, 8 crcL, 9 crcH
    this.tampon = new Uint8Array(255);
    this.tramesValides = 0;
    this.erreursCrc = 0;
    this.erreursVersion = 0;
  }

  /** Consomme un tableau d'octets ; renvoie la liste des trames complètes. */
  pousser(octets) {
    const trames = [];
    for (const o of octets) {
      const t = this.pousserOctet(o);
      if (t) trames.push(t);
    }
    return trames;
  }

  pousserOctet(o) {
    switch (this.etat) {
      case 0: if (o === 0xaa) this.etat = 1; break;
      case 1: this.etat = o === 0x55 ? 2 : o === 0xaa ? 1 : 0; break;
      case 2:
        if (o !== VERSION) { this.erreursVersion++; this.etat = 0; break; }
        this.crc = crc16([o]); this.etat = 3; break;
      case 3: this.type = o; this.crc = crc16([o], 0, 1, this.crc); this.etat = 4; break;
      case 4: this.sequence = o; this.crc = crc16([o], 0, 1, this.crc); this.etat = 5; break;
      case 5: this.sequence |= o << 8; this.crc = crc16([o], 0, 1, this.crc); this.etat = 6; break;
      case 6:
        this.longueur = o; this.index = 0; this.crc = crc16([o], 0, 1, this.crc);
        this.etat = o === 0 ? 8 : 7; break;
      case 7:
        this.tampon[this.index++] = o; this.crc = crc16([o], 0, 1, this.crc);
        if (this.index >= this.longueur) this.etat = 8;
        break;
      case 8: this.crcRecu = o; this.etat = 9; break;
      case 9: {
        this.etat = 0;
        if ((this.crcRecu | (o << 8)) === this.crc) {
          this.tramesValides++;
          return { type: this.type, sequence: this.sequence, donnees: this.tampon.slice(0, this.longueur) };
        }
        this.erreursCrc++;
        break;
      }
      default: this.etat = 0;
    }
    return null;
  }
}

export class Sequenceur {
  constructor(initial = 0) { this.valeur = initial & 0xffff; }
  suivant() { const v = this.valeur; this.valeur = (this.valeur + 1) & 0xffff; return v; }
}

// ---------------------------------------------------------------------------
// Lecture / écriture little-endian
// ---------------------------------------------------------------------------
const TAILLES = { u8: 1, i8: 1, u16: 2, i16: 2, u32: 4, i32: 4 };

class Ecrivain {
  constructor(taille) { this.vue = new DataView(new ArrayBuffer(taille)); this.pos = 0; }
  ecrire(format, v) {
    const d = this.vue;
    switch (format) {
      case "u8": d.setUint8(this.pos, v); break;
      case "i8": d.setInt8(this.pos, v); break;
      case "u16": d.setUint16(this.pos, v, true); break;
      case "i16": d.setInt16(this.pos, Math.max(-32768, Math.min(32767, v)), true); break;
      case "u32": d.setUint32(this.pos, v, true); break;
      case "i32": d.setInt32(this.pos, v, true); break;
      default: throw new Error(format);
    }
    this.pos += TAILLES[format];
    return this;
  }
  octets(tab) { new Uint8Array(this.vue.buffer).set(tab, this.pos); this.pos += tab.length; return this; }
  sommets(liste) { for (const [lat, lon] of liste) this.ecrire("i32", lat).ecrire("i32", lon); return this; }
  resultat() { return new Uint8Array(this.vue.buffer, 0, this.pos); }
}

class Lecteur {
  constructor(octets) {
    this.octetsBruts = octets;
    this.vue = new DataView(octets.buffer, octets.byteOffset, octets.byteLength);
    this.pos = 0;
  }
  lire(format) {
    if (this.pos + TAILLES[format] > this.vue.byteLength) throw new ErreurProtocole("charge utile trop courte");
    const d = this.vue;
    let v;
    switch (format) {
      case "u8": v = d.getUint8(this.pos); break;
      case "i8": v = d.getInt8(this.pos); break;
      case "u16": v = d.getUint16(this.pos, true); break;
      case "i16": v = d.getInt16(this.pos, true); break;
      case "u32": v = d.getUint32(this.pos, true); break;
      case "i32": v = d.getInt32(this.pos, true); break;
      default: throw new Error(format);
    }
    this.pos += TAILLES[format];
    return v;
  }
  sommets(n) {
    const r = [];
    for (let i = 0; i < n; i++) r.push([this.lire("i32"), this.lire("i32")]);
    return r;
  }
  reste() { const r = this.octetsBruts.slice(this.pos); this.pos = this.vue.byteLength; return r; }
}

// ---------------------------------------------------------------------------
// Schémas des messages à taille fixe : [nom du champ, format]
// ---------------------------------------------------------------------------
export const SCHEMAS = {
  [TYPE.HEARTBEAT]: [["emetteur", "u8"], ["etat", "u8"], ["temps_ms", "u32"]],
  [TYPE.ACK]: [["type_acquitte", "u8"], ["sequence_acquittee", "u16"]],
  [TYPE.NACK]: [["type_refuse", "u8"], ["sequence_refusee", "u16"], ["code", "u8"]],
  [TYPE.TELEMETRIE]: [["temps_ms", "u32"], ["roulis_cdeg", "i16"], ["tangage_cdeg", "i16"], ["lacet_cdeg", "u16"],
    ["latitude_e7", "i32"], ["longitude_e7", "i32"], ["altitude_msl_cm", "i32"], ["altitude_relative_cm", "i32"],
    ["vitesse_sol_cms", "u16"], ["vitesse_verticale_cms", "i16"], ["route_cdeg", "u16"],
    ["tension_batterie_mv", "u16"], ["courant_batterie_ca", "i16"], ["batterie_pct", "u8"], ["mode_vol", "u8"],
    ["etat_gps", "u8"], ["nb_satellites", "u8"], ["hdop_x100", "u16"], ["drapeaux", "u8"],
    ["waypoint_courant", "u16"], ["photos_declenchees", "u16"]],
  [TYPE.ALERTE_AVARIE]: [["code", "u8"], ["gravite", "u8"], ["source", "u8"], ["action", "u8"], ["valeur", "i16"],
    ["actif", "u8"]],
  [TYPE.COMMANDE_MODE]: [["mode_vol", "u8"]],
  [TYPE.COMMANDE_MANUELLE]: [["roulis", "i16"], ["tangage", "i16"], ["lacet", "i16"], ["gaz", "i16"]],
  [TYPE.ATTERRISSAGE]: [],
  [TYPE.RETOUR_MAISON]: [],
  [TYPE.ARRET_URGENCE]: [["cle", "u16"]],
  [TYPE.MISSION_DEBUT]: [["id_mission", "u16"], ["nb_waypoints", "u16"], ["nb_sommets_limites", "u8"],
    ["nb_zones", "u8"], ["distance_photos_cm", "u16"], ["vitesse_cms", "u16"], ["options", "u8"],
    ["hauteur_max_m", "u8"]],
  [TYPE.MISSION_WAYPOINT]: [["id_mission", "u16"], ["index", "u16"], ["latitude_e7", "i32"],
    ["longitude_e7", "i32"], ["altitude_relative_cm", "i32"], ["vitesse_cms", "u16"], ["action", "u8"]],
  [TYPE.MISSION_FIN]: [["id_mission", "u16"], ["crc_mission", "u16"]],
  [TYPE.MISSION_ACK]: [["id_mission", "u16"], ["element", "u8"], ["index", "u16"], ["statut", "u8"]],
  [TYPE.MISSION_VERIFICATION]: [["id_mission", "u16"], ["element", "u8"], ["index", "u16"]],
};

// ---------------------------------------------------------------------------
// Messages à taille variable
// ---------------------------------------------------------------------------
function verifierSommets(n) {
  if (n < 3 || n > SOMMETS_MAX_TRAME) throw new ErreurProtocole(`nombre de sommets invalide : ${n}`);
}

const VARIABLES = {
  [TYPE.TEXTE]: {
    encoder(m) {
      let texte = m.texte;
      let octets = new TextEncoder().encode(texte);
      while (octets.length > 200) { texte = texte.slice(0, -1); octets = new TextEncoder().encode(texte); }
      return new Ecrivain(2 + octets.length).ecrire("u8", m.gravite).ecrire("u8", m.source).octets(octets).resultat();
    },
    decoder(l) { return { gravite: l.lire("u8"), source: l.lire("u8"), texte: new TextDecoder().decode(l.reste()) }; },
  },
  [TYPE.DISTANCES_TOURELLE]: {
    encoder(m) {
      const e = new Ecrivain(5 + 2 * m.distances_cm.length).ecrire("u8", m.distances_cm.length)
        .ecrire("i16", m.angle_debut_cdeg).ecrire("i16", m.pas_cdeg);
      for (const d of m.distances_cm) e.ecrire("u16", d);
      return e.resultat();
    },
    decoder(l) {
      const n = l.lire("u8");
      const m = { angle_debut_cdeg: l.lire("i16"), pas_cdeg: l.lire("i16"), distances_cm: [] };
      for (let i = 0; i < n; i++) m.distances_cm.push(l.lire("u16"));
      return m;
    },
  },
  [TYPE.MISSION_LIMITES]: {
    encoder(m) {
      verifierSommets(m.sommets.length);
      return new Ecrivain(3 + 8 * m.sommets.length).ecrire("u16", m.id_mission).ecrire("u8", m.sommets.length)
        .sommets(m.sommets).resultat();
    },
    decoder(l) {
      const id = l.lire("u16");
      const n = l.lire("u8");
      verifierSommets(n);
      return { id_mission: id, sommets: l.sommets(n) };
    },
  },
  [TYPE.ZONE_INTERDITE]: {
    encoder(m) {
      verifierSommets(m.sommets.length);
      return new Ecrivain(4 + 8 * m.sommets.length).ecrire("u16", m.id_mission).ecrire("u8", m.index_zone)
        .ecrire("u8", m.sommets.length).sommets(m.sommets).resultat();
    },
    decoder(l) {
      const id = l.lire("u16");
      const index = l.lire("u8");
      const n = l.lire("u8");
      verifierSommets(n);
      return { id_mission: id, index_zone: index, sommets: l.sommets(n) };
    },
  },
};

/** Encode la charge utile d'un message à partir de ses champs. */
export function encoderMessage(type, champs = {}) {
  const variable = VARIABLES[type];
  if (variable) return variable.encoder(champs);
  const schema = SCHEMAS[type];
  if (!schema) throw new ErreurProtocole(`type inconnu : ${nomType(type)}`);
  const e = new Ecrivain(schema.reduce((s, [, f]) => s + TAILLES[f], 0));
  for (const [nom, format] of schema) {
    const v = champs[nom];
    if (v === undefined) throw new ErreurProtocole(`${nomType(type)} : champ ${nom} manquant`);
    e.ecrire(format, v);
  }
  return e.resultat();
}

/** Décode la charge utile d'une trame. Les octets en trop sont ignorés. */
export function decoderMessage(type, donnees) {
  const l = new Lecteur(donnees);
  const variable = VARIABLES[type];
  if (variable) return variable.decoder(l);
  const schema = SCHEMAS[type];
  if (!schema) return { inconnu: true, donnees };
  const m = {};
  for (const [nom, format] of schema) m[nom] = l.lire(format);
  return m;
}

/** Raccourci : trame complète d'un message. */
export function trameMessage(type, sequence, champs) {
  return encoderTrame(type, sequence, encoderMessage(type, champs));
}

/** Référence { element, index } d'un message de mission, ou null. */
export function referenceElement(type, m) {
  switch (type) {
    case TYPE.MISSION_DEBUT: return { element: ELEMENT.DEBUT, index: 0 };
    case TYPE.MISSION_LIMITES: return { element: ELEMENT.LIMITES, index: 0 };
    case TYPE.ZONE_INTERDITE: return { element: ELEMENT.ZONE, index: m.index_zone };
    case TYPE.MISSION_WAYPOINT: return { element: ELEMENT.WAYPOINT, index: m.index };
    default: return null;
  }
}

// ---------------------------------------------------------------------------
// Outils
// ---------------------------------------------------------------------------
export function versHex(octets) {
  return Array.from(octets, (o) => o.toString(16).padStart(2, "0")).join("");
}

export function depuisHex(hex) {
  const propre = hex.replace(/[\s:]/g, "");
  if (propre.length % 2 !== 0 || /[^0-9a-fA-F]/.test(propre)) throw new Error("hexadécimal invalide");
  const r = new Uint8Array(propre.length / 2);
  for (let i = 0; i < r.length; i++) r[i] = parseInt(propre.substr(2 * i, 2), 16);
  return r;
}

export function egaux(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

export const e7 = (degres) => Math.round(degres * 1e7);
export const depuisE7 = (entier) => entier / 1e7;
