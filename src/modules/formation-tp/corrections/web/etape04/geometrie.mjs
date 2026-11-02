// =============================================================================
// Étape 4 — CORRECTION : géométrie du terrain
// (référence complète : planificateur/js/geometrie.js)
//
// Conventions (les mêmes que le planificateur) :
//   point géographique : [lat, lon] en degrés ;
//   point en mètres    : { x, y }, x vers l'est, y vers le nord ;
//   polygone           : tableau de sommets, sans répéter le premier à la fin.
// =============================================================================

const M_PAR_DEGRE_LAT = 111132.92;
const M_PAR_DEGRE_LON_EQUATEUR = 111320;

/** 1. Projection locale autour de `origine` : sur une parcelle, la Terre est plate à quelques mm près. */
export function versMetres([lat0, lon0], [lat, lon]) {
  return {
    x: (lon - lon0) * M_PAR_DEGRE_LON_EQUATEUR * Math.cos((lat0 * Math.PI) / 180),
    y: (lat - lat0) * M_PAR_DEGRE_LAT,
  };
}

/** Inverse de versMetres. */
export function versGeo([lat0, lon0], { x, y }) {
  return [lat0 + y / M_PAR_DEGRE_LAT, lon0 + x / (M_PAR_DEGRE_LON_EQUATEUR * Math.cos((lat0 * Math.PI) / 180))];
}

/** Produit vectoriel (b − a) × (c − a) : > 0 si c est à gauche de a→b. */
const orientation = (a, b, c) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);

/** 2. Aire par la formule du lacet : ½ |Σ (xᵢ yᵢ₊₁ − xᵢ₊₁ yᵢ)|. */
export function aire(poly) {
  let s = 0;
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i];
    const b = poly[(i + 1) % poly.length];
    s += a.x * b.y - b.x * a.y;
  }
  return Math.abs(s) / 2;
}

/** c (colinéaire à [a, b]) est-il sur le segment ? */
const surSegment = (a, b, c) =>
  Math.min(a.x, b.x) <= c.x && c.x <= Math.max(a.x, b.x) && Math.min(a.y, b.y) <= c.y && c.y <= Math.max(a.y, b.y);

/**
 * 3. Les segments [a, b] et [c, d] se coupent-ils (contact compris) ?
 * Ils se coupent si c et d sont de part et d'autre de (ab) ET a et b de part
 * et d'autre de (cd) ; cas particuliers : points alignés sur l'autre segment.
 */
export function segmentsSeCoupent(a, b, c, d) {
  const o1 = orientation(a, b, c);
  const o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a);
  const o4 = orientation(c, d, b);
  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) return true;
  return (o1 === 0 && surSegment(a, b, c)) || (o2 === 0 && surSegment(a, b, d)) ||
    (o3 === 0 && surSegment(c, d, a)) || (o4 === 0 && surSegment(c, d, b));
}

/** 4. Polygone simple : au moins 3 sommets et aucun côté ne coupe un côté non adjacent. */
export function estSimple(poly) {
  const n = poly.length;
  if (n < 3) return false;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const adjacents = j === i + 1 || (i === 0 && j === n - 1);
      if (adjacents) continue;
      if (segmentsSeCoupent(poly[i], poly[(i + 1) % n], poly[j], poly[(j + 1) % n])) return false;
    }
  }
  return true;
}

/**
 * 5. Point dans un polygone : on compte les côtés traversés par une demi-droite
 * horizontale partant du point vers la droite ; impair = dedans.
 */
export function contient(poly, p) {
  let dedans = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if ((a.y > p.y) !== (b.y > p.y)) {
      const xCroisement = a.x + ((p.y - a.y) * (b.x - a.x)) / (b.y - a.y);
      if (p.x < xCroisement) dedans = !dedans;
    }
  }
  return dedans;
}
