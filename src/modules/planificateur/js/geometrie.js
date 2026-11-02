// Géométrie plane pour la planification : projection locale en mètres,
// polygones, segments, distances, intervalles.

/** Projection locale autour d'une origine : x vers l'est, y vers le nord, en mètres. */
export class ProjectionLocale {
  constructor(latOrigine, lonOrigine) {
    this.lat0 = latOrigine;
    this.lon0 = lonOrigine;
    const phi = (latOrigine * Math.PI) / 180;
    this.mLat = 111132.92 - 559.82 * Math.cos(2 * phi) + 1.175 * Math.cos(4 * phi) - 0.0023 * Math.cos(6 * phi);
    this.mLon = 111412.84 * Math.cos(phi) - 93.5 * Math.cos(3 * phi) + 0.118 * Math.cos(5 * phi);
  }

  /** [lat, lon] (degrés) -> {x, y} (mètres) */
  versXY([lat, lon]) {
    return { x: (lon - this.lon0) * this.mLon, y: (lat - this.lat0) * this.mLat };
  }

  /** {x, y} (mètres) -> [lat, lon] (degrés) */
  versGeo({ x, y }) {
    return [this.lat0 + y / this.mLat, this.lon0 + x / this.mLon];
  }

  static autourDe(points) {
    const n = points.length;
    return new ProjectionLocale(points.reduce((s, p) => s + p[0], 0) / n, points.reduce((s, p) => s + p[1], 0) / n);
  }
}

// --- vecteurs --------------------------------------------------------------
export const plus = (a, b) => ({ x: a.x + b.x, y: a.y + b.y });
export const moins = (a, b) => ({ x: a.x - b.x, y: a.y - b.y });
export const fois = (a, k) => ({ x: a.x * k, y: a.y * k });
export const scalaire = (a, b) => a.x * b.x + a.y * b.y;
export const vectoriel = (a, b) => a.x * b.y - a.y * b.x;
export const norme = (a) => Math.hypot(a.x, a.y);
export const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
export function tourner(p, angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  return { x: c * p.x - s * p.y, y: s * p.x + c * p.y };
}

// --- polygones -------------------------------------------------------------

/** Aire signée (formule du lacet), positive dans le sens trigonométrique. */
export function aireSignee(p) {
  let s = 0;
  for (let i = 0; i < p.length; i++) s += vectoriel(p[i], p[(i + 1) % p.length]);
  return s / 2;
}

export function perimetre(p) {
  let s = 0;
  for (let i = 0; i < p.length; i++) s += distance(p[i], p[(i + 1) % p.length]);
  return s;
}

const orientation = (a, b, c) => vectoriel(moins(b, a), moins(c, a));

function surSegment(a, b, p) {
  return p.x >= Math.min(a.x, b.x) - 1e-9 && p.x <= Math.max(a.x, b.x) + 1e-9 &&
    p.y >= Math.min(a.y, b.y) - 1e-9 && p.y <= Math.max(a.y, b.y) + 1e-9;
}

/** Les segments [a,b] et [c,d] se touchent-ils (extrémités comprises) ? */
export function segmentsSeCoupent(a, b, c, d) {
  const o1 = orientation(a, b, c);
  const o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a);
  const o4 = orientation(c, d, b);
  const eps = 1e-12;
  if (((o1 > eps && o2 < -eps) || (o1 < -eps && o2 > eps)) && ((o3 > eps && o4 < -eps) || (o3 < -eps && o4 > eps))) {
    return true;
  }
  return (Math.abs(o1) <= eps && surSegment(a, b, c)) || (Math.abs(o2) <= eps && surSegment(a, b, d)) ||
    (Math.abs(o3) <= eps && surSegment(c, d, a)) || (Math.abs(o4) <= eps && surSegment(c, d, b));
}

/** Polygone simple : aucune arête ne coupe une arête non voisine. */
export function estSimple(p) {
  const n = p.length;
  if (n < 3) return false;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue;
      if (segmentsSeCoupent(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n])) return false;
    }
  }
  return true;
}

/** Point dans le polygone (lancer de rayon). */
export function contient(p, q) {
  let dedans = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const a = p[i];
    const b = p[j];
    if ((a.y > q.y) !== (b.y > q.y) && q.x < ((b.x - a.x) * (q.y - a.y)) / (b.y - a.y) + a.x) dedans = !dedans;
  }
  return dedans;
}

export function distancePointSegment(q, a, b) {
  const ab = moins(b, a);
  const l2 = scalaire(ab, ab);
  if (l2 === 0) return distance(q, a);
  const t = Math.max(0, Math.min(1, scalaire(moins(q, a), ab) / l2));
  return distance(q, plus(a, fois(ab, t)));
}

export function distanceSegmentSegment(a, b, c, d) {
  if (segmentsSeCoupent(a, b, c, d)) return 0;
  return Math.min(distancePointSegment(a, c, d), distancePointSegment(b, c, d),
    distancePointSegment(c, a, b), distancePointSegment(d, a, b));
}

/** Distance du segment [a,b] au bord du polygone p. */
export function distanceSegmentBord(a, b, p) {
  let m = Infinity;
  for (let i = 0; i < p.length; i++) m = Math.min(m, distanceSegmentSegment(a, b, p[i], p[(i + 1) % p.length]));
  return m;
}

/** Le segment est-il entièrement dans le polygone (extrémités dedans, aucun côté traversé) ? */
export function segmentDansPolygone(a, b, p) {
  if (!contient(p, a) || !contient(p, b)) return false;
  for (let i = 0; i < p.length; i++) if (segmentsSeCoupent(a, b, p[i], p[(i + 1) % p.length])) return false;
  return true;
}

/** Le segment touche-t-il le polygone (traversée ou extrémité dedans) ? */
export function segmentTouchePolygone(a, b, p) {
  if (contient(p, a) || contient(p, b)) return true;
  for (let i = 0; i < p.length; i++) if (segmentsSeCoupent(a, b, p[i], p[(i + 1) % p.length])) return true;
  return false;
}

/** Enveloppe convexe (chaîne monotone d'Andrew). */
export function enveloppeConvexe(points) {
  const p = [...points].sort((u, v) => u.x - v.x || u.y - v.y);
  if (p.length < 3) return p;
  const bas = [];
  for (const v of p) {
    while (bas.length >= 2 && orientation(bas[bas.length - 2], bas[bas.length - 1], v) <= 0) bas.pop();
    bas.push(v);
  }
  const haut = [];
  for (let i = p.length - 1; i >= 0; i--) {
    const v = p[i];
    while (haut.length >= 2 && orientation(haut[haut.length - 2], haut[haut.length - 1], v) <= 0) haut.pop();
    haut.push(v);
  }
  bas.pop();
  haut.pop();
  return bas.concat(haut);
}

// --- intervalles sur une droite horizontale -------------------------------
// Un intervalle est [a, b] avec a < b. Les listes sont triées et disjointes.

/** Abscisses où la droite y = cste coupe les arêtes (triées). Règle demi-ouverte aux sommets. */
export function intersectionsHorizontale(p, y) {
  const xs = [];
  for (let i = 0; i < p.length; i++) {
    const a = p[i];
    const b = p[(i + 1) % p.length];
    if ((a.y > y) !== (b.y > y)) xs.push(a.x + ((y - a.y) * (b.x - a.x)) / (b.y - a.y));
  }
  return xs.sort((u, v) => u - v);
}

/** Intervalles de la droite y = cste situés à l'intérieur du polygone. */
export function intervallesDedans(p, y) {
  const xs = intersectionsHorizontale(p, y);
  const r = [];
  for (let i = 0; i + 1 < xs.length; i += 2) if (xs[i + 1] > xs[i]) r.push([xs[i], xs[i + 1]]);
  return r;
}

/**
 * Intervalle des x tels que le point (x, y) soit à moins de r du segment [A,B]
 * (intersection de la droite avec la « gélule » autour du segment). Calcul exact :
 * union des deux disques des extrémités et de la bande centrale, qui est un
 * intervalle car la gélule est convexe.
 */
export function intervalleGelule(A, B, r, y) {
  const morceaux = [];
  for (const C of [A, B]) {
    const dy = y - C.y;
    if (Math.abs(dy) < r) {
      const h = Math.sqrt(r * r - dy * dy);
      morceaux.push([C.x - h, C.x + h]);
    }
  }
  const L = distance(A, B);
  if (L > 1e-12) {
    const d = { x: (B.x - A.x) / L, y: (B.y - A.y) / L };
    // t(x) = (x - A.x) d.x + (y - A.y) d.y  dans [0, L]
    // s(x) = -(x - A.x) d.y + (y - A.y) d.x  dans ]-r, r[
    let bas = -Infinity;
    let haut = Infinity;
    const contrainte = (coef, constante, min, max) => {
      // min < coef * x + constante < max
      if (Math.abs(coef) < 1e-12) {
        if (constante <= min || constante >= max) { bas = Infinity; haut = -Infinity; }
        return;
      }
      let x1 = (min - constante) / coef;
      let x2 = (max - constante) / coef;
      if (x1 > x2) [x1, x2] = [x2, x1];
      bas = Math.max(bas, x1);
      haut = Math.min(haut, x2);
    };
    contrainte(d.x, -A.x * d.x + (y - A.y) * d.y, 0, L);
    contrainte(-d.y, A.x * d.y + (y - A.y) * d.x, -r, r);
    if (haut > bas) morceaux.push([bas, haut]);
  }
  if (morceaux.length === 0) return null;
  return [Math.min(...morceaux.map((m) => m[0])), Math.max(...morceaux.map((m) => m[1]))];
}

/** Soustrait l'intervalle [a, b] d'une liste d'intervalles. */
export function soustraire(liste, [a, b]) {
  const r = [];
  for (const [u, v] of liste) {
    if (b <= u || a >= v) { r.push([u, v]); continue; }
    if (a > u) r.push([u, a]);
    if (b < v) r.push([b, v]);
  }
  return r;
}

/** Ensemble des x de la droite y à distance >= marge de toutes les arêtes de p. */
export function retirerBords(liste, p, marge, y) {
  let r = liste;
  if (marge <= 0) return r;
  for (let i = 0; i < p.length && r.length; i++) {
    const g = intervalleGelule(p[i], p[(i + 1) % p.length], marge, y);
    if (g) r = soustraire(r, g);
  }
  return r;
}
