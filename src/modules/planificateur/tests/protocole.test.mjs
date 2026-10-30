// Tests du planificateur (Node 20+) :  node --test planificateur/tests/
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import * as p from "../js/protocole.js";

const vecteurs = JSON.parse(readFileSync(new URL("../../protocole/vecteurs_test.json", import.meta.url), "utf8"));

test("CRC de contrôle", () => {
  for (const v of vecteurs.crc) assert.equal(p.crc16(new TextEncoder().encode(v.ascii)), v.crc);
});

test("chaque vecteur : décodage, champs et ré-encodage identiques", () => {
  for (const v of vecteurs.trames) {
    const octets = p.depuisHex(v.hex);
    const t = p.decoderTrame(octets);
    assert.equal(t.type, v.type, v.nom);
    assert.equal(t.sequence, v.sequence, v.nom);
    const m = p.decoderMessage(t.type, t.donnees);
    for (const [nom, valeur] of Object.entries(v.champs)) assert.deepEqual(m[nom], valeur, `${v.nom}.${nom}`);
    assert.equal(p.versHex(p.trameMessage(v.type, v.sequence, v.champs)), v.hex, v.nom);
  }
});

test("flux : bruit, trame corrompue, paquets de toutes tailles", () => {
  const f = vecteurs.flux;
  const octets = p.depuisHex(f.hex);
  for (const taille of [1, 3, 20, 182, 1000]) {
    const d = new p.DecodeurTrames();
    const trames = [];
    for (let i = 0; i < octets.length; i += taille) trames.push(...d.pousser(octets.slice(i, i + taille)));
    assert.deepEqual(trames.map((t) => p.versHex(p.encoderTrame(t.type, t.sequence, t.donnees))), f.trames_attendues);
    assert.equal(d.erreursCrc, f.erreurs_crc);
  }
});

test("CRC d'une mission complète", () => {
  const m = vecteurs.mission;
  let crc = 0xffff;
  for (const h of [m.debut_hex, m.limites_hex, ...m.zones_hex, ...m.waypoints_hex]) {
    const d = p.depuisHex(h);
    crc = p.crc16(d, 0, d.length, crc);
  }
  assert.equal(crc, m.crc);
});

test("polygone de moins de 3 sommets refusé", () => {
  assert.throws(() => p.encoderMessage(p.TYPE.MISSION_LIMITES, { id_mission: 1, sommets: [[0, 0], [1, 1]] }));
});
