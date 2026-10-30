// Critères de réussite de l'étape 4 (géométrie).
//   npm test                 → votre fichier geometrie.mjs
//   npm run test:corrections → la correction (tp/corrections/web)
import { test } from "node:test";
import assert from "node:assert/strict";

const dossier = process.env.TP_CORRECTIONS ? "../../corrections/web/etape04/" : "./";
const G = await import(new URL(dossier + "geometrie.mjs", import.meta.url));

const proche = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ""} ${a} ≠ ${b} (± ${tol})`);
const carre = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }, { x: 0, y: 10 }];

test("ex1 — projection locale et retour", () => {
  const o = [48, 2];
  const nord = G.versMetres(o, [48.001, 2]);
  proche(nord.x, 0, 1e-9, "x");
  proche(nord.y, 111.13, 0.5, "y (1/1000 de degré de latitude)");
  const est = G.versMetres(o, [48, 2.001]);
  proche(est.x, 74.49, 0.4, "x (1/1000 de degré de longitude à 48°)");
  const [lat, lon] = G.versGeo(o, G.versMetres(o, [48.0123, 2.0456]));
  proche(lat, 48.0123, 1e-9, "lat");
  proche(lon, 2.0456, 1e-9, "lon");
});

test("ex2 — aire", () => {
  proche(G.aire([{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 50 }, { x: 0, y: 50 }]), 5000, 1e-9);
  proche(G.aire([{ x: 0, y: 50 }, { x: 100, y: 50 }, { x: 100, y: 0 }, { x: 0, y: 0 }]), 5000, 1e-9, "sens horaire");
  proche(G.aire([{ x: 0, y: 0 }, { x: 4, y: 0 }, { x: 0, y: 3 }]), 6, 1e-9, "triangle");
});

test("ex3 — segments qui se coupent", () => {
  const P = (x, y) => ({ x, y });
  assert.equal(G.segmentsSeCoupent(P(0, 0), P(10, 10), P(0, 10), P(10, 0)), true, "en X");
  assert.equal(G.segmentsSeCoupent(P(0, 0), P(10, 0), P(0, 1), P(10, 1)), false, "parallèles");
  assert.equal(G.segmentsSeCoupent(P(0, 0), P(10, 0), P(5, 0), P(5, 5)), true, "en T (contact)");
  assert.equal(G.segmentsSeCoupent(P(0, 0), P(10, 0), P(5, 0), P(15, 0)), true, "alignés, chevauchement");
  assert.equal(G.segmentsSeCoupent(P(0, 0), P(10, 0), P(11, 0), P(15, 0)), false, "alignés, disjoints");
  assert.equal(G.segmentsSeCoupent(P(0, 0), P(10, 0), P(5, 1), P(5, 5)), false, "presque en T");
});

test("ex4 — polygone simple", () => {
  assert.equal(G.estSimple(carre), true, "carré");
  assert.equal(G.estSimple([{ x: 0, y: 0 }, { x: 10, y: 10 }, { x: 10, y: 0 }, { x: 0, y: 10 }]), false, "papillon");
  const enL = [{ x: 0, y: 0 }, { x: 60, y: 0 }, { x: 60, y: 20 }, { x: 20, y: 20 }, { x: 20, y: 60 }, { x: 0, y: 60 }];
  assert.equal(G.estSimple(enL), true, "en L (concave)");
  assert.equal(G.estSimple([{ x: 0, y: 0 }, { x: 1, y: 1 }]), false, "2 sommets");
});

test("ex5 — point dans un polygone", () => {
  assert.equal(G.contient(carre, { x: 5, y: 5 }), true);
  assert.equal(G.contient(carre, { x: 15, y: 5 }), false);
  const enL = [{ x: 0, y: 0 }, { x: 60, y: 0 }, { x: 60, y: 20 }, { x: 20, y: 20 }, { x: 20, y: 60 }, { x: 0, y: 60 }];
  assert.equal(G.contient(enL, { x: 10, y: 50 }), true, "dans la branche du L");
  assert.equal(G.contient(enL, { x: 40, y: 40 }), false, "dans le creux du L");
});
