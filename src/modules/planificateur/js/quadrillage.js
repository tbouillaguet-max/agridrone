// Génération automatique d'un quadrillage « en aller-retour » qui couvre le
// terrain en évitant les zones interdites.
//
// Étapes :
//  1. projection en mètres et rotation pour que les passes soient horizontales
//     (direction choisie pour minimiser le nombre de passes) ;
//  2. sur chaque passe, intervalles « libres » = dans les limites, hors des
//     zones, à distance des bords (marges) ;
//  3. regroupement des intervalles en CELLULES : une cellule est une suite de
//     passes voisines qui se recouvrent une à une (décomposition dite
//     « boustrophédon ») ; une zone au milieu du champ crée des cellules à
//     gauche, à droite, dessous et dessus ;
//  4. chaque cellule est parcourue en aller-retour ; on enchaîne les cellules
//     en allant à chaque fois vers l'entrée la plus proche ;
//  5. chaque liaison qui couperait une zone ou sortirait des limites est
//     remplacée par un détour : plus court chemin dans le « graphe de
//     visibilité » des coins des obstacles (algorithme de Dijkstra).

import * as G from "./geometrie.js";
import { ACTION } from "./protocole.js";
import { calculerPrisesDeVue } from "./calculs.js";

const EPS = 0.01; // tolérance de 1 cm sur les marges

/**
 * @returns {{ok:boolean, erreur?:string, waypoints:Array, nbPasses:number, nbCellules:number,
 *            capPassesDeg:number, prisesDeVue:object}}
 */
export function genererQuadrillage({ limites, zones = [], parametres, camera, tech, depart = null }) {
  const vide = (erreur) => ({ ok: false, erreur, waypoints: [], nbPasses: 0, nbCellules: 0, capPassesDeg: 0,
    prisesDeVue: null });
  if (!limites || limites.length < 3) return vide("tracez d'abord les limites du terrain");
  const proj = G.ProjectionLocale.autourDe(limites);
  let L = limites.map((p) => proj.versXY(p));
  if (!G.estSimple(L) || Math.abs(G.aireSignee(L)) < 1) return vide("les limites ne forment pas un polygone valide");
  const Z = [];
  for (const z of zones) {
    const zx = z.map((p) => proj.versXY(p));
    if (zx.length < 3 || !G.estSimple(zx)) return vide("une zone interdite n'est pas un polygone valide");
    Z.push(zx);
  }
  const pdv = calculerPrisesDeVue(parametres, camera, tech);
  if (!(pdv.espacementPassesM > 0.1) || !(pdv.distancePhotosM > 0.05)) return vide("paramètres photo invalides");
  const margeL = Math.max(0, parametres.margeLimitesM ?? 0);
  const margeZ = Math.max(0, parametres.margeZonesM ?? 0);

  // --- 1. Direction et rotation -------------------------------------------
  const angle = parametres.capPassesDeg == null || parametres.capPassesDeg === ""
    ? angleAutomatique(L)
    : ((90 - Number(parametres.capPassesDeg)) * Math.PI) / 180;
  const capPassesDeg = ((((90 - (angle * 180) / Math.PI) % 180) + 180) % 180);
  const R = (p) => G.tourner(p, -angle);
  const Rinv = (p) => G.tourner(p, angle);
  L = L.map(R);
  const ZR = Z.map((z) => z.map(R));

  // --- 2. Intervalles libres sur chaque passe -----------------------------
  const longueurMin = Math.max(1, pdv.distancePhotosM);
  const intervallesLibres = (y) => {
    let libres = G.retirerBords(G.intervallesDedans(L, y), L, margeL, y);
    for (const z of ZR) {
      for (const iv of G.intervallesDedans(z, y)) libres = G.soustraire(libres, iv);
      libres = G.retirerBords(libres, z, margeZ, y);
    }
    return libres.filter(([a, b]) => b - a >= longueurMin);
  };
  const ys = L.map((p) => p.y);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const largeur = yMax - yMin;
  const e = pdv.espacementPassesM;
  // Nombre de passes pour couvrir toute la largeur : (n − 1) × espacement + emprise ≥ largeur
  const nbLignes = Math.max(1, Math.ceil((largeur - pdv.empriseLargeurM) / e - 1e-9) + 1);
  if (nbLignes > 2000) return vide("trop de passes : augmentez l'altitude ou réduisez le recouvrement latéral");
  // Bande « utile » (là où une passe est possible malgré les marges), trouvée par échantillonnage
  const pas = Math.min(e / 10, 0.25);
  let yUtileMin = null;
  let yUtileMax = null;
  for (let y = yMin + pas / 2; y < yMax; y += pas) {
    if (intervallesLibres(y).length) {
      if (yUtileMin === null) yUtileMin = y;
      yUtileMax = y;
    }
  }
  if (yUtileMin === null) {
    return vide("aucune passe possible : terrain trop étroit pour les marges, ou entièrement couvert par les zones");
  }
  // Passes centrées sur le terrain, ramenées dans la bande utile si besoin
  const decalage = (largeur - (nbLignes - 1) * e) / 2;
  const positions = [];
  for (let k = 0; k < nbLignes; k++) {
    const y = Math.min(Math.max(yMin + decalage + k * e, yUtileMin), yUtileMax);
    if (!positions.length || y - positions[positions.length - 1] > e / 2) positions.push(y);
  }
  const lignes = positions.map((y, k) => ({ k, y, intervalles: intervallesLibres(y) }));

  // --- 3. Cellules ---------------------------------------------------------
  const cellules = construireCellules(lignes);

  // --- 4. Ordre de parcours -------------------------------------------------
  let position = depart ? R(proj.versXY(depart)) : null;
  const restantes = new Set(cellules);
  const parcours = [];
  while (restantes.size) {
    let meilleur = null;
    for (const c of restantes) {
      for (const v of variantes(c)) {
        const entree = v[0][0];
        const cout = position ? G.distance(position, entree) : entree.y * 1e6 + entree.x;
        if (!meilleur || cout < meilleur.cout) meilleur = { c, v, cout };
      }
    }
    parcours.push(meilleur.v);
    restantes.delete(meilleur.c);
    const dernier = meilleur.v[meilleur.v.length - 1];
    position = dernier[1];
  }

  // --- 5. Chemin avec détours ----------------------------------------------
  const sur = (a, b) => segmentSur(a, b, L, ZR, margeL, margeZ);
  const graphe = new GrapheVisibilite(noeudsDeContournement(L, ZR, margeL, margeZ), sur);
  const chemin = [];
  for (const segments of parcours) {
    for (const [a, b] of segments) {
      if (chemin.length) {
        const precedent = chemin[chemin.length - 1].p;
        if (!sur(precedent, a)) {
          const detour = graphe.plusCourtChemin(precedent, a);
          if (!detour) return vide("impossible de contourner une zone interdite : agrandissez le passage ou réduisez les marges");
          for (const p of detour) chemin.push({ p, action: ACTION.PASSAGE });
        }
      }
      chemin.push({ p: a, action: ACTION.DEBUT_PHOTOS });
      chemin.push({ p: b, action: ACTION.FIN_PHOTOS });
    }
  }

  const waypoints = chemin.map(({ p, action }) => {
    const [lat, lon] = proj.versGeo(Rinv(p));
    return { lat, lon, altitudeM: parametres.altitudeM, vitesseMs: pdv.vitesseMs, action };
  });
  return {
    ok: true, waypoints, nbPasses: lignes.filter((l) => l.intervalles.length).length, nbCellules: cellules.length,
    capPassesDeg, prisesDeVue: pdv,
  };
}

/** Direction des passes qui minimise la largeur à couvrir (côtés de l'enveloppe convexe). */
export function angleAutomatique(poly) {
  const env = G.enveloppeConvexe(poly);
  let meilleur = { largeur: Infinity, angle: 0, cote: 0 };
  for (let i = 0; i < env.length; i++) {
    const a = env[i];
    const b = env[(i + 1) % env.length];
    const cote = G.distance(a, b);
    if (cote < 1e-6) continue;
    const n = { x: -(b.y - a.y) / cote, y: (b.x - a.x) / cote };
    const proj = env.map((p) => G.scalaire(p, n));
    const largeur = Math.max(...proj) - Math.min(...proj);
    if (largeur < meilleur.largeur - 0.01 || (Math.abs(largeur - meilleur.largeur) <= 0.01 && cote > meilleur.cote)) {
      meilleur = { largeur, angle: Math.atan2(b.y - a.y, b.x - a.x), cote };
    }
  }
  let a = meilleur.angle;
  while (a <= -Math.PI / 2) a += Math.PI;
  while (a > Math.PI / 2) a -= Math.PI;
  return a;
}

/**
 * Regroupe les intervalles en cellules : un intervalle prolonge une cellule
 * s'il est le SEUL à recouvrir le dernier intervalle de cette cellule et
 * qu'il ne recouvre qu'elle. Sinon (séparation ou fusion autour d'une zone),
 * de nouvelles cellules commencent.
 */
export function construireCellules(lignes) {
  const chevauche = (u, v) => Math.min(u[1], v[1]) - Math.max(u[0], v[0]) > 0.5;
  const cellules = [];
  let ouvertes = [];
  for (const ligne of lignes) {
    const candidats = ligne.intervalles.map((iv) => ouvertes.filter((o) => chevauche(o.dernier, iv)));
    const compte = new Map();
    for (const liste of candidats) for (const o of liste) compte.set(o, (compte.get(o) ?? 0) + 1);
    const suivantes = [];
    ligne.intervalles.forEach((iv, j) => {
      const c = candidats[j];
      const segment = { y: ligne.y, a: iv[0], b: iv[1] };
      if (c.length === 1 && compte.get(c[0]) === 1) {
        c[0].cellule.push(segment);
        suivantes.push({ cellule: c[0].cellule, dernier: iv });
      } else {
        const cellule = [segment];
        cellules.push(cellule);
        suivantes.push({ cellule, dernier: iv });
      }
    });
    ouvertes = suivantes;
  }
  return cellules;
}

/** Les 4 façons de parcourir une cellule (de bas en haut ou de haut en bas, en partant à gauche ou à droite). */
function variantes(cellule) {
  const r = [];
  for (const ordre of [cellule, [...cellule].reverse()]) {
    for (const departGauche of [true, false]) {
      r.push(ordre.map((s, i) => {
        const versDroite = (i % 2 === 0) === departGauche;
        const g = { x: s.a, y: s.y };
        const d = { x: s.b, y: s.y };
        return versDroite ? [g, d] : [d, g];
      }));
    }
  }
  return r;
}

/** Un tronçon est sûr s'il reste dans les limites et hors des zones, avec les marges. */
export function segmentSur(a, b, L, Z, margeL, margeZ) {
  if (!G.segmentDansPolygone(a, b, L)) return false;
  if (margeL > 0 && G.distanceSegmentBord(a, b, L) < margeL - EPS) return false;
  for (const z of Z) {
    if (G.segmentTouchePolygone(a, b, z)) return false;
    if (margeZ > 0 && G.distanceSegmentBord(a, b, z) < margeZ - EPS) return false;
  }
  return true;
}

/**
 * Points de contournement : coins saillants des zones repoussés vers
 * l'extérieur, et coins rentrants des limites repoussés vers l'intérieur
 * (un plus court chemin autour d'obstacles polygonaux ne tourne qu'en ces points).
 */
export function noeudsDeContournement(L, Z, margeL, margeZ) {
  const noeuds = [];
  const sensDirect = (p) => (G.aireSignee(p) > 0 ? p : [...p].reverse());
  // Zones : coins convexes, vers l'extérieur
  for (const z of Z) noeuds.push(...decaler(sensDirect(z), margeZ + 0.5, +1, true));
  // Limites : coins rentrants, vers l'intérieur
  noeuds.push(...decaler(sensDirect(L), margeL + 0.5, -1, false));
  return noeuds;
}

/**
 * Décale les coins d'un polygone (sens direct) le long de la bissectrice.
 * sens = +1 : vers l'extérieur ; -1 : vers l'intérieur. `convexes` choisit
 * les coins convexes (true) ou rentrants (false).
 */
function decaler(p, distanceDecalage, sens, convexes) {
  const r = [];
  const n = p.length;
  for (let i = 0; i < n; i++) {
    const a = p[(i - 1 + n) % n];
    const b = p[i];
    const c = p[(i + 1) % n];
    const convexe = G.vectoriel(G.moins(b, a), G.moins(c, b)) > 0;
    if (convexe !== convexes) continue;
    // normales extérieures des deux côtés (polygone direct : l'extérieur est à droite)
    const n1 = normaliser({ x: b.y - a.y, y: -(b.x - a.x) });
    const n2 = normaliser({ x: c.y - b.y, y: -(c.x - b.x) });
    const bis = normaliser(G.plus(n1, n2));
    const cosDemi = Math.max(0.3, G.scalaire(bis, n1));
    r.push(G.plus(b, G.fois(bis, (sens * distanceDecalage) / cosDemi)));
  }
  return r;
}

function normaliser(v) {
  const l = G.norme(v) || 1;
  return { x: v.x / l, y: v.y / l };
}

/** Graphe de visibilité entre points de contournement, avec plus court chemin (Dijkstra). */
export class GrapheVisibilite {
  constructor(noeuds, sur) {
    this.noeuds = noeuds;
    this.sur = sur;
    const n = noeuds.length;
    this.visible = Array.from({ length: n }, () => new Array(n).fill(false));
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        if (sur(noeuds[i], noeuds[j])) this.visible[i][j] = this.visible[j][i] = true;
      }
    }
  }

  /** Points intermédiaires du plus court chemin sûr de a à b (sans a ni b), ou null. */
  plusCourtChemin(a, b) {
    const n = this.noeuds.length;
    const N = n + 2; // indices n = a, n + 1 = b
    const point = (i) => (i < n ? this.noeuds[i] : i === n ? a : b);
    const versA = this.noeuds.map((p) => this.sur(a, p));
    const versB = this.noeuds.map((p) => this.sur(p, b));
    const voisins = (i) => {
      const r = [];
      if (i === n) { versA.forEach((v, j) => v && r.push(j)); }
      else if (i < n) {
        for (let j = 0; j < n; j++) if (this.visible[i][j]) r.push(j);
        if (versB[i]) r.push(n + 1);
      }
      return r;
    };
    const dist = new Array(N).fill(Infinity);
    const precedent = new Array(N).fill(-1);
    const fait = new Array(N).fill(false);
    dist[n] = 0;
    for (;;) {
      let u = -1;
      for (let i = 0; i < N; i++) if (!fait[i] && dist[i] < Infinity && (u < 0 || dist[i] < dist[u])) u = i;
      if (u < 0) return null;
      if (u === n + 1) break;
      fait[u] = true;
      for (const v of voisins(u)) {
        const d = dist[u] + G.distance(point(u), point(v));
        if (d < dist[v]) { dist[v] = d; precedent[v] = u; }
      }
    }
    const chemin = [];
    for (let i = precedent[n + 1]; i !== n; i = precedent[i]) chemin.unshift(this.noeuds[i]);
    return chemin;
  }
}
