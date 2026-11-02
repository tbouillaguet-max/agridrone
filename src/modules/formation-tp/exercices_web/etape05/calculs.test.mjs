// Critères de réussite de l'étape 5 (calculs, passes, vérifications).
import { test } from "node:test";
import assert from "node:assert/strict";

const dossier = process.env.TP_CORRECTIONS ? "../../corrections/web/etape05/" : "./";
const C = await import(new URL(dossier + "calculs.mjs", import.meta.url));

const proche = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ""} ${a} ≠ ${b} (± ${tol})`);
// Caméra d'exemple (12 Mpx, capteur 7,2 × 5,4 mm, focale 5,4 mm)
const camera = { capteurLargeurMm: 7.2, capteurHauteurMm: 5.4, focaleMm: 5.4, imageLargeurPx: 4000, imageHauteurPx: 3000, intervalleMinS: 0.7 };

test("ex1 — prises de vue à 10 m", () => {
  const r = C.prisesDeVue({ altitudeM: 10, recouvrementFrontalPct: 75, recouvrementLateralPct: 65, vitesseMaxMs: 5, flouMaxPx: 1 }, camera);
  proche(r.empriseLargeurM, 13.333, 0.001, "emprise transversale");
  proche(r.empriseLongueurM, 10, 1e-9, "emprise longitudinale");
  proche(r.gsdMm, 3.333, 0.001, "GSD");
  proche(r.espacementPassesM, 4.667, 0.001, "espacement des passes");
  proche(r.distancePhotosM, 2.5, 1e-9, "distance entre photos");
  proche(r.vitesseMs, 3.571, 0.001, "vitesse limitée par la cadence (2,5 m / 0,7 s)");
  proche(r.expositionMaxUs, 933, 1, "exposition maximale");
});

test("ex2 — passes sur un rectangle", () => {
  const p = C.passesRectangle(100, 60, 10, 5);
  assert.equal(p.length, 12, "6 passes de 2 waypoints");
  assert.deepEqual(p.slice(0, 4), [{ x: 5, y: 5, action: 1 }, { x: 95, y: 5, action: 2 }, { x: 95, y: 15, action: 1 }, { x: 5, y: 15, action: 2 }]);
  assert.deepEqual(p.at(-1), { x: 5, y: 55, action: 2 });
  const q = C.passesRectangle(100, 60, 12, 5);       // ⌈50 / 12⌉ + 1 = 6 passes, espacées de 10 m
  assert.equal(q.length, 12);
  proche(q[2].y - q[0].y, 10, 1e-9, "espacement réel ≤ espacement demandé");
  assert.deepEqual(C.passesRectangle(100, 8, 10, 5), [{ x: 5, y: 4, action: 1 }, { x: 95, y: 4, action: 2 }], "bande nulle : une passe au milieu");
});

test("ex3 à ex5 — longueur, photos, durée", () => {
  const p = C.passesRectangle(100, 60, 10, 5);
  proche(C.longueur(p), 6 * 90 + 5 * 10, 1e-9, "longueur");
  assert.equal(C.nombrePhotos(p, 2.5), 6 * 37, "photos (1 + 36 par passe de 90 m)");
  assert.equal(C.nombrePhotos([{ x: 0, y: 0, action: 1 }, { x: 10, y: 0, action: 2 }], 3), 5, "0, 3, 6, 9 et 10 m");
  proche(C.duree(p, 3, 10), 590 / 3 + 30 + 20 / 1.5, 1e-9, "durée");
});

test("ex6 — vérifications", () => {
  const limites = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 60 }, { x: 0, y: 60 }];
  const zone = [{ x: 40, y: 25 }, { x: 60, y: 25 }, { x: 60, y: 35 }, { x: 40, y: 35 }];
  const p = C.passesRectangle(100, 60, 10, 5);
  assert.deepEqual(C.verifierChemin(limites, [], p, 150), [], "sans zone : tout va bien");
  assert.deepEqual(C.verifierChemin(limites, [zone], p, 150), ["tronçon 4 traverse la zone 0", "tronçon 6 traverse la zone 0"]);
  assert.deepEqual(C.verifierChemin(limites, [], p, 10), ["trop de waypoints (12 > 10)"]);
  assert.deepEqual(C.verifierChemin(limites, [], [{ x: 50, y: 30, action: 0 }, { x: 120, y: 30, action: 0 }], 150),
    ["waypoint 1 hors des limites", "tronçon 0 coupe les limites"]);
  const papillon = [{ x: 0, y: 0 }, { x: 10, y: 10 }, { x: 10, y: 0 }, { x: 0, y: 10 }];
  assert.ok(C.verifierChemin(papillon, [], [], 150).includes("limites invalides"));
});
