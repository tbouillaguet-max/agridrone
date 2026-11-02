// =============================================================================
// Étape 4 — géométrie du terrain (voir tp/etape_04_carte_web.md)
// Tests :  cd tp/exercices_web && npm test
//
// Conventions (les mêmes que le planificateur) :
//   point géographique : [lat, lon] en degrés ;
//   point en mètres    : { x, y }, x vers l'est, y vers le nord ;
//   polygone           : tableau de sommets, sans répéter le premier à la fin.
// =============================================================================

const aFaire = (n) => { throw new Error(`À compléter : étape 4, exercice ${n}`); };

/**
 * 1. Projection locale autour de `origine` : 1° de latitude = 111 132,92 m ;
 * 1° de longitude = 111 320 m × cos(latitude de l'origine).
 */
export function versMetres(origine, p) { return aFaire(1); }

/** 1 bis. Inverse : { x, y } (mètres autour de `origine`) → [lat, lon]. */
export function versGeo(origine, v) { return aFaire(1); }

/** 2. Aire en m² (formule du lacet), toujours positive, quel que soit le sens de parcours. */
export function aire(poly) { return aFaire(2); }

/**
 * 3. Les segments [a, b] et [c, d] se coupent-ils ? Un contact (extrémité sur
 * l'autre segment, segments alignés qui se chevauchent) compte comme une coupure.
 * Indice : produit vectoriel (b − a) × (c − a).
 */
export function segmentsSeCoupent(a, b, c, d) { return aFaire(3); }

/** 4. Polygone simple : au moins 3 sommets et aucun côté ne coupe un côté NON adjacent. */
export function estSimple(poly) { return aFaire(4); }

/** 5. Le point p est-il à l'intérieur du polygone ? (demi-droite horizontale, règle pair / impair) */
export function contient(poly, p) { return aFaire(5); }
