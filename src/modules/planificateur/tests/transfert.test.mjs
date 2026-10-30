import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { connect } from "node:net";

import { crcMission, elementsMission, nouvelleMission, versJson, depuisJson } from "../js/mission.js";
import { DecodeurTrames, TYPE, STATUT, depuisHex, versHex, decoderMessage } from "../js/protocole.js";
import { AU2Simule } from "../js/au2_simule.js";
import { verifierMission, envoiPossible, CODE } from "../js/verifications.js";
import { TransfertMission } from "../js/transfert.js";
import { genererQuadrillage } from "../js/quadrillage.js";
import { CONFIG } from "../js/config.js";
import { camera, capacites, geo, parametres, rectangle, tech } from "./outils.mjs";

const vecteurs = JSON.parse(readFileSync(new URL("../../protocole/vecteurs_test.json", import.meta.url), "utf8"));

function missionExemple() {
  const m = nouvelleMission(CONFIG);
  m.culture = "ble";
  m.limites = rectangle(80, 40);
  m.zones = [geo([[30, 15], [40, 15], [35, 25]])];
  const r = genererQuadrillage({ limites: m.limites, zones: m.zones, parametres: parametres({ altitudeM: 8 }), camera, tech });
  assert.ok(r.ok, r.erreur);
  m.waypoints = r.waypoints;
  return { m, pdv: r.prisesDeVue };
}

test("CRC de mission identique aux vecteurs partagés", () => {
  const v = vecteurs.mission;
  const elements = [v.debut_hex, v.limites_hex, ...v.zones_hex, ...v.waypoints_hex].map((h) => ({ donnees: depuisHex(h) }));
  assert.equal(crcMission(elements), v.crc);
});

test("conversion d'une mission en éléments : mêmes octets que les vecteurs partagés", () => {
  const v = vecteurs.mission;
  const debut = decoderMessage(TYPE.MISSION_DEBUT, depuisHex(v.debut_hex));
  const limites = decoderMessage(TYPE.MISSION_LIMITES, depuisHex(v.limites_hex));
  const zones = v.zones_hex.map((h) => decoderMessage(TYPE.ZONE_INTERDITE, depuisHex(h)));
  const wps = v.waypoints_hex.map((h) => decoderMessage(TYPE.MISSION_WAYPOINT, depuisHex(h)));
  const m = {
    idMission: debut.id_mission,
    limites: limites.sommets.map(([a, b]) => [a / 1e7, b / 1e7]),
    zones: zones.map((z) => z.sommets.map(([a, b]) => [a / 1e7, b / 1e7])),
    waypoints: wps.map((w) => ({ lat: w.latitude_e7 / 1e7, lon: w.longitude_e7 / 1e7,
      altitudeM: w.altitude_relative_cm / 100, vitesseMs: w.vitesse_cms / 100, action: w.action })),
    parametres: { finMission: "retour" },
  };
  const { elements } = elementsMission(m, { distancePhotosM: 1.8, vitesseMs: 2.5 });
  const attendus = [v.limites_hex, ...v.zones_hex, ...v.waypoints_hex];
  assert.deepEqual(elements.slice(1).map((e) => versHex(e.donnees)), attendus);
  const d = elements[0].champs;
  assert.deepEqual([d.id_mission, d.nb_waypoints, d.nb_sommets_limites, d.nb_zones, d.distance_photos_cm, d.vitesse_cms, d.options],
    [debut.id_mission, debut.nb_waypoints, debut.nb_sommets_limites, debut.nb_zones, debut.distance_photos_cm, debut.vitesse_cms, debut.options]);
});

test("transfert complet vers AU2 simulé (morceaux de 20 octets) : mission validée", async () => {
  const { m, pdv } = missionExemple();
  const au2 = new AU2Simule({ capacites, taillePaquet: 20 });
  const textes = [];
  au2.ajouterEcouteur((t) => { if (t.type === TYPE.TEXTE) textes.push(decoderMessage(t.type, t.donnees).texte); });
  const tr = new TransfertMission(au2, { delaiReponseMs: 200 });
  const { elements, crc } = elementsMission(m, pdv);
  const phases = new Set();
  const r = await tr.transferer(elements, m.idMission, crc, (phase) => phases.add(phase));
  assert.ok(r.succes, r.message);
  assert.deepEqual([...phases], ["envoi", "relecture", "fin"]);
  assert.ok(au2.missionValidee);
  await new Promise((ok) => setTimeout(ok, 20));
  assert.ok(textes.some((t) => t.includes("validée")), textes.join(" | "));
});

test("drone armé : mission refusée (ETAT_INCOMPATIBLE) ; désarmé après l'atterrissage : nouvelle mission acceptée", async () => {
  const { m, pdv } = missionExemple();
  const au2 = new AU2Simule({ capacites });
  const tr = new TransfertMission(au2, { delaiReponseMs: 100 });
  const { elements, crc } = elementsMission(m, pdv);
  assert.ok((await tr.transferer(elements, m.idMission, crc)).succes);
  au2.arme = true; // en vol
  const m2 = { ...m, idMission: m.idMission + 1 };
  const e2 = elementsMission(m2, pdv);
  const refus = await tr.transferer(e2.elements, m2.idMission, e2.crc);
  assert.equal(refus.succes, false);
  assert.equal(refus.code, STATUT.ETAT_INCOMPATIBLE);
  assert.ok(au2.missionValidee, "la mission en cours reste chargée");
  au2.arme = false; // posé et désarmé automatiquement
  const ok = await tr.transferer(e2.elements, m2.idMission, e2.crc);
  assert.ok(ok.succes, ok.message);
  assert.equal(au2.debut.id_mission, m2.idMission);
});

test("transfert malgré des pertes (réémissions)", async () => {
  const { m, pdv } = missionExemple();
  const au2 = new AU2Simule({ capacites, taillePaquet: 64, pertes: 0.15 });
  const tr = new TransfertMission(au2, { delaiReponseMs: 60, essais: 12 });
  const { elements, crc } = elementsMission(m, pdv);
  const r = await tr.transferer(elements, m.idMission, crc);
  assert.ok(r.succes, r.message);
});

test("stockage défaillant : la relecture le détecte, la mission n'est pas validée", async () => {
  const { m, pdv } = missionExemple();
  const abimer = (type, d) => {
    if (type !== TYPE.MISSION_WAYPOINT) return d;
    const c = d.slice();
    c[12] ^= 1; // altitude modifiée
    return c;
  };
  const au2 = new AU2Simule({ capacites, abimer });
  const tr = new TransfertMission(au2, { delaiReponseMs: 100 });
  const { elements, crc } = elementsMission(m, pdv);
  const r = await tr.transferer(elements, m.idMission, crc);
  assert.equal(r.succes, false);
  assert.equal(r.code, STATUT.RELECTURE_DIFFERENTE);
  assert.equal(au2.missionValidee, false);
});

test("capacité dépassée signalée dès l'en-tête", async () => {
  const { m, pdv } = missionExemple();
  const au2 = new AU2Simule({ capacites: { ...capacites, maxWaypoints: 3 } });
  const tr = new TransfertMission(au2, { delaiReponseMs: 100 });
  const { elements, crc } = elementsMission(m, pdv);
  const r = await tr.transferer(elements, m.idMission, crc);
  assert.equal(r.succes, false);
  assert.equal(r.code, STATUT.CAPACITE_DEPASSEE);
});

test("fichier JSON : enregistrement puis relecture à l'identique, fichiers invalides refusés", () => {
  const { m } = missionExemple();
  const relu = depuisJson(versJson(m), CONFIG);
  assert.deepEqual(relu.limites, m.limites);
  assert.deepEqual(relu.waypoints, m.waypoints);
  assert.equal(relu.idMission, m.idMission);
  assert.throws(() => depuisJson("pas du json", CONFIG));
  assert.throws(() => depuisJson(JSON.stringify({ version: 99 }), CONFIG));
  assert.throws(() => depuisJson(JSON.stringify({ ...m, limites: [[200, 0]] }), CONFIG));
});

test("culture : enregistrée dans le JSON, contrôlée à la lecture, obligatoire avant l'envoi", () => {
  const { m } = missionExemple();
  const relu = depuisJson(versJson(m), CONFIG);
  assert.equal(JSON.parse(versJson(m)).culture, "ble");
  assert.equal(relu.culture, "ble");
  // Ancien fichier sans culture : chargé, culture à choisir (choix forcé avant l'envoi)
  const { culture, ...sansCulture } = m;
  assert.equal(culture, "ble");
  assert.equal(depuisJson(JSON.stringify(sansCulture), CONFIG).culture, null);
  // Culture inconnue : erreur explicite
  assert.throws(() => depuisJson(JSON.stringify({ ...m, culture: "vigne" }), CONFIG), /culture « vigne » inconnue/);
  for (const c of ["ble", "mais", "pommier"]) assert.equal(depuisJson(JSON.stringify({ ...m, culture: c }), CONFIG).culture, c);

  const verifier = (culture) => verifierMission({ ...m, culture }, capacites, { culturesAdmises: ["ble", "mais", "pommier"] });
  assert.equal(verifier(null).find((c) => c.code === CODE.CULTURE).etat, "erreur");
  assert.equal(envoiPossible(verifier(null)), false);
  assert.equal(verifier("vigne").find((c) => c.code === CODE.CULTURE).etat, "erreur");
  assert.equal(verifier("mais").find((c) => c.code === CODE.CULTURE).etat, "ok");
  assert.ok(envoiPossible(verifier("mais")));
});

test("culture NON transmise au drone : trames identiques quelle que soit la culture", () => {
  const { m, pdv } = missionExemple();
  const hex = (culture) => elementsMission({ ...m, culture }, pdv).elements.map((e) => versHex(e.donnees)).join("|");
  assert.equal(hex("ble"), hex("pommier"));
  assert.equal(hex("ble"), hex(null));
});

// Test croisé facultatif : le planificateur (JavaScript) envoie une mission au
// croquis banc_au2_mission (C++) exécuté sur PC. Lancer d'abord :
//   make -C protocole/arduino/test_hote banc && ./protocole/arduino/test_hote/banc_hote 5761
// puis : BANC_AU2=127.0.0.1:5761 npm test
const banc = process.env.BANC_AU2;
test("transfert vers le banc AU2 en C++ (BANC_AU2=hôte:port)", { skip: !banc && "BANC_AU2 non défini" }, async () => {
  const [hote, port] = banc.split(":");
  const socket = connect(Number(port), hote);
  await new Promise((ok, ko) => { socket.once("connect", ok); socket.once("error", ko); });
  const decodeur = new DecodeurTrames();
  const ecouteurs = [];
  socket.on("data", (d) => { for (const t of decodeur.pousser(new Uint8Array(d))) for (const f of ecouteurs) f(t); });
  const canal = {
    ajouterEcouteur: (f) => ecouteurs.push(f),
    envoyerTrame: (o) => new Promise((ok) => socket.write(o, ok)),
  };
  try {
    const { m, pdv } = missionExemple();
    const tr = new TransfertMission(canal, { delaiReponseMs: 500 });
    const { elements, crc } = elementsMission(m, pdv);
    const r = await tr.transferer(elements, m.idMission, crc);
    assert.ok(r.succes, r.message);
  } finally {
    socket.destroy();
  }
});
