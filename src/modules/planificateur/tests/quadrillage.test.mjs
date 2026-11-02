import assert from "node:assert/strict";
import { test } from "node:test";

import * as G from "../js/geometrie.js";
import { ACTION } from "../js/protocole.js";
import { calculerPrisesDeVue, statistiquesChemin } from "../js/calculs.js";
import { genererQuadrillage } from "../js/quadrillage.js";
import { verifierMission, envoiPossible, CODE } from "../js/verifications.js";
import { camera, capacites, drone, geo, parametres, proj, rectangle, tech, xy } from "./outils.mjs";

function generer(limites, zones = [], modifs = {}) {
  return genererQuadrillage({ limites, zones, parametres: parametres(modifs), camera, tech });
}

/** Vérifie les propriétés de sécurité d'un chemin généré. */
function verifierSecurite(r, limites, zones, margeL, margeZ) {
  const L = limites.map(xy);
  const Z = zones.map((z) => z.map(xy));
  const P = r.waypoints.map((w) => xy([w.lat, w.lon]));
  for (let i = 1; i < P.length; i++) {
    assert.ok(G.segmentDansPolygone(P[i - 1], P[i], L), `tronçon ${i} sort des limites`);
    assert.ok(G.distanceSegmentBord(P[i - 1], P[i], L) >= margeL - 0.02, `tronçon ${i} trop près des limites`);
    for (const z of Z) {
      assert.ok(!G.segmentTouchePolygone(P[i - 1], P[i], z), `tronçon ${i} traverse une zone`);
      assert.ok(G.distanceSegmentBord(P[i - 1], P[i], z) >= margeZ - 0.02, `tronçon ${i} trop près d'une zone`);
    }
  }
}

/** Part de la surface autorisée couverte par les photos (échantillonnage en grille). */
function couverture(r, limites, zones, margeZ) {
  const L = limites.map(xy);
  const Z = zones.map((z) => z.map(xy));
  const P = r.waypoints.map((w) => ({ ...xy([w.lat, w.lon]), action: w.action }));
  const demiLargeur = r.prisesDeVue.empriseLargeurM / 2;
  const segments = [];
  for (let i = 0; i + 1 < P.length; i++) if (P[i].action === ACTION.DEBUT_PHOTOS) segments.push([P[i], P[i + 1]]);
  const xs = L.map((p) => p.x);
  const ys = L.map((p) => p.y);
  let total = 0;
  let couverts = 0;
  for (let x = Math.min(...xs); x <= Math.max(...xs); x += 1) {
    for (let y = Math.min(...ys); y <= Math.max(...ys); y += 1) {
      const q = { x, y };
      if (!G.contient(L, q)) continue;
      if (Z.some((z) => G.contient(z, q) || G.distanceSegmentBord(q, q, z) < margeZ + demiLargeur)) continue;
      total++;
      if (segments.some(([a, b]) => G.distancePointSegment(q, a, b) <= demiLargeur)) couverts++;
    }
  }
  return couverts / total;
}

test("emprise, résolution au sol et espacements (caméra d'essai à 10 m)", () => {
  const pdv = calculerPrisesDeVue(parametres({ altitudeM: 10 }), camera, tech);
  assert.ok(Math.abs(pdv.empriseLargeurM - 13.333) < 0.01);
  assert.ok(Math.abs(pdv.empriseLongueurM - 10) < 0.01);
  assert.ok(Math.abs(pdv.gsdMm - 3.333) < 0.01);
  assert.ok(Math.abs(pdv.espacementPassesM - 13.333 * 0.3) < 0.01);
  assert.ok(Math.abs(pdv.distancePhotosM - 2.5) < 0.01);
  // cadence : 2,5 m toutes les 0,7 s => 3,57 m/s, donc la vitesse par défaut (3 m/s) est gardée
  assert.equal(pdv.vitesseMs, 3);
});

test("rectangle sans zone : passes parallèles au grand côté, en aller-retour, dans les marges", () => {
  const limites = rectangle(100, 50);
  const r = generer(limites, [], { altitudeM: 10 });
  assert.ok(r.ok, r.erreur);
  assert.ok(Math.abs(r.capPassesDeg - 90) < 0.5, `cap ${r.capPassesDeg}`);
  assert.equal(r.nbCellules, 1);
  // (n − 1) × espacement + emprise ≥ 50 m
  const n = Math.ceil((50 - r.prisesDeVue.empriseLargeurM) / r.prisesDeVue.espacementPassesM) + 1;
  assert.equal(r.nbPasses, n);
  assert.equal(r.waypoints.length, 2 * n);
  verifierSecurite(r, limites, [], 2, 3);
  // chaque passe va de 2 m à 98 m (marge de 2 m)
  const [a, b] = r.waypoints.slice(0, 2).map((w) => xy([w.lat, w.lon]));
  assert.ok(Math.abs(G.distance(a, b) - 96) < 0.05);
  assert.ok(couverture(r, limites, [], 3) > 0.99);
});

test("zone interdite au milieu : contournée, jamais traversée, terrain couvert", () => {
  const limites = rectangle(120, 80);
  const zones = [geo([[50, 30], [70, 30], [70, 50], [50, 50]])];
  const r = generer(limites, zones, { altitudeM: 8 });
  assert.ok(r.ok, r.erreur);
  assert.ok(r.nbCellules >= 3, `${r.nbCellules} cellules`);
  verifierSecurite(r, limites, zones, 2, 3);
  assert.ok(couverture(r, limites, zones, 3) > 0.97);
  const controles = verifierMission({ limites, zones, waypoints: r.waypoints }, capacites,
    { margeLimitesM: 2, margeZonesM: 3 });
  assert.ok(envoiPossible(controles), JSON.stringify(controles.filter((c) => c.etat !== "ok")));
});

test("terrain en L et zone triangulaire près du bord", () => {
  const limites = geo([[0, 0], [100, 0], [100, 40], [40, 40], [40, 100], [0, 100]]);
  const zones = [geo([[60, 10], [80, 10], [70, 28]])];
  const r = generer(limites, zones, { altitudeM: 6 });
  assert.ok(r.ok, r.erreur);
  verifierSecurite(r, limites, zones, 2, 3);
  assert.ok(couverture(r, limites, zones, 3) > 0.95);
});

test("deux zones et cap imposé", () => {
  const limites = rectangle(150, 100);
  const zones = [geo([[30, 30], [45, 30], [45, 45], [30, 45]]), geo([[100, 50], [120, 55], [110, 75]])];
  const r = generer(limites, zones, { altitudeM: 10, capPassesDeg: 0 });
  assert.ok(r.ok, r.erreur);
  assert.ok(Math.abs(r.capPassesDeg) < 0.5 || Math.abs(r.capPassesDeg - 180) < 0.5);
  verifierSecurite(r, limites, zones, 2, 3);
});

test("terrain trop étroit pour les marges", () => {
  const r = generer(rectangle(100, 3), [], { margeLimitesM: 2 });
  assert.equal(r.ok, false);
});

test("limites croisées refusées", () => {
  const r = generer(geo([[0, 0], [50, 50], [50, 0], [0, 50]]));
  assert.equal(r.ok, false);
});

test("statistiques et énergie", () => {
  const limites = rectangle(100, 50);
  const r = generer(limites, [], { altitudeM: 10 });
  const s = statistiquesChemin(r.waypoints, {
    distancePhotosM: r.prisesDeVue.distancePhotosM, depart: proj.versGeo({ x: -10, y: 0 }), retourMaison: true, drone,
  });
  // longueur = passes (96 m chacune) + liaisons entre passes (espacement)
  const n = r.nbPasses;
  const attendu = 96 * n + r.prisesDeVue.espacementPassesM * (n - 1);
  assert.ok(Math.abs(s.longueurM - attendu) < 0.5, `${s.longueurM} au lieu de ${attendu}`);
  // photos : 96 m / 2,5 m = 38,4 => 1 + 38 + 1 par passe
  assert.equal(s.nbPhotos, 40 * n);
  assert.ok(s.transitM > 10);
  assert.ok(Math.abs(s.energieWh - (drone.puissanceMoyenneW * s.dureeS) / 3600) < 1e-9);
});

test("vérifications : waypoint manuel hors limites et altitude interdite", () => {
  const limites = rectangle(100, 50);
  const wps = [
    { ...pointGeo(10, 10), altitudeM: 5, vitesseMs: 2, action: ACTION.PHOTO_UNIQUE },
    { ...pointGeo(120, 10), altitudeM: 5, vitesseMs: 2, action: ACTION.PASSAGE },
  ];
  let c = verifierMission({ limites, zones: [], waypoints: wps }, capacites);
  assert.equal(c.find((x) => x.code === CODE.WAYPOINTS_DEDANS).etat, "erreur");
  wps[1] = { ...pointGeo(90, 10), altitudeM: 500, vitesseMs: 2, action: ACTION.PASSAGE };
  c = verifierMission({ limites, zones: [], waypoints: wps }, capacites);
  assert.equal(c.find((x) => x.code === CODE.ALTITUDES).etat, "erreur");
  assert.equal(envoiPossible(c), false);
});

function pointGeo(x, y) {
  const [lat, lon] = proj.versGeo({ x, y });
  return { lat, lon };
}

// ---------------------------------------------------------------------------
// Test aléatoire : sur 60 terrains et jeux de zones tirés au hasard, soit le
// générateur refuse proprement, soit son chemin est sûr (jamais dans une zone,
// jamais hors des limites, marges respectées).
// ---------------------------------------------------------------------------
function aleatoire(graine) {
  let s = graine;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

/** Polygone « étoilé » (toujours simple) autour d'un centre. */
function etoile(alea, cx, cy, rMin, rMax, n) {
  const angles = Array.from({ length: n }, () => alea() * 2 * Math.PI).sort((a, b) => a - b);
  return angles.map((a) => {
    const r = rMin + alea() * (rMax - rMin);
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
}

test("aléatoire : un chemin généré est toujours sûr", () => {
  const alea = aleatoire(12345);
  let reussis = 0;
  for (let cas = 0; cas < 60; cas++) {
    const limites = geo(etoile(alea, 0, 0, 40, 110, 5 + Math.floor(alea() * 8)));
    const zones = [];
    for (let z = 0; z < Math.floor(alea() * 4); z++) {
      zones.push(geo(etoile(alea, (alea() - 0.5) * 120, (alea() - 0.5) * 120, 4, 15, 3 + Math.floor(alea() * 5))));
    }
    const r = generer(limites, zones, { altitudeM: 6 + alea() * 20, capPassesDeg: alea() < 0.5 ? null : alea() * 180 });
    if (!r.ok) continue;
    reussis++;
    verifierSecurite(r, limites, zones, 2, 3);
  }
  assert.ok(reussis > 40, `seulement ${reussis} cas générés`);
});
