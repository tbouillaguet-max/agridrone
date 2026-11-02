// =============================================================================
// Étape 5 — CORRECTION : calculs photographiques, passes, vérifications
// (référence complète : planificateur/js/calculs.js, quadrillage.js, verifications.js)
// Points en mètres : { x, y } ; waypoints : { x, y, action } (0 passage, 1 début photos, 2 fin, 3 photo unique).
// =============================================================================
import { contient, estSimple, segmentsSeCoupent } from "../etape04/geometrie.mjs";

/**
 * 1. Prises de vue. Le grand côté de l'image est perpendiculaire aux passes.
 *   emprise = hauteur × taille du capteur / focale ; GSD = emprise / pixels ;
 *   espacement des passes = largeur × (1 − recouvrement latéral) ;
 *   distance entre photos = longueur × (1 − recouvrement frontal) ;
 *   vitesse = min(vitesse max, distance entre photos / intervalle minimal) ;
 *   exposition max = flou admis (px) × GSD / vitesse.
 */
export function prisesDeVue(p, camera) {
  const empriseLargeurM = (p.altitudeM * camera.capteurLargeurMm) / camera.focaleMm;
  const empriseLongueurM = (p.altitudeM * camera.capteurHauteurMm) / camera.focaleMm;
  const gsdM = empriseLargeurM / camera.imageLargeurPx;
  const espacementPassesM = empriseLargeurM * (1 - p.recouvrementLateralPct / 100);
  const distancePhotosM = empriseLongueurM * (1 - p.recouvrementFrontalPct / 100);
  const vitesseMs = Math.min(p.vitesseMaxMs, distancePhotosM / camera.intervalleMinS);
  const expositionMaxUs = ((p.flouMaxPx * gsdM) / vitesseMs) * 1e6;
  return { empriseLargeurM, empriseLongueurM, gsdMm: gsdM * 1000, espacementPassesM, distancePhotosM, vitesseMs, expositionMaxUs };
}

/**
 * 2. Passes parallèles à x sur le rectangle [0, largeur] × [0, hauteur], à
 * `marge` des bords : n = ⌈(hauteur − 2 marge) / espacement⌉ + 1 passes réparties
 * régulièrement de y = marge à y = hauteur − marge (une seule au milieu si la
 * bande est nulle), parcourues en aller-retour en commençant en bas à gauche.
 */
export function passesRectangle(largeurM, hauteurM, espacementM, margeM) {
  const bande = hauteurM - 2 * margeM;
  const n = bande <= 0 ? 1 : Math.ceil(bande / espacementM) + 1;
  const points = [];
  for (let i = 0; i < n; i++) {
    const y = n === 1 ? hauteurM / 2 : margeM + (i * bande) / (n - 1);
    const [xa, xb] = i % 2 === 0 ? [margeM, largeurM - margeM] : [largeurM - margeM, margeM];
    points.push({ x: xa, y, action: 1 }, { x: xb, y, action: 2 });
  }
  return points;
}

/** 3. Longueur d'un chemin. */
export function longueur(points) {
  let l = 0;
  for (let i = 1; i < points.length; i++) l += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
  return l;
}

/** 4. Nombre de photos : même règle que l'étape 3 (photo finale si le reste dépasse 10 % du pas). */
export function nombrePhotos(points, pasM) {
  let n = 0;
  let actives = false;
  let depuis = 0;
  for (let i = 0; i < points.length; i++) {
    if (i > 0 && actives) {
      depuis += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
      while (depuis >= pasM) { n++; depuis -= pasM; }
    }
    const a = points[i].action;
    if (a === 1) { n++; actives = true; depuis = 0; }
    else if (a === 2) { if (actives && depuis > 0.1 * pasM) n++; actives = false; }
    else if (a === 3) n++;
  }
  return n;
}

/** 5. Durée (s) : trajet à vitesse constante + 3 s par waypoint intermédiaire + montée et descente à 1,5 m/s. */
export function duree(points, vitesseMs, altitudeM) {
  return longueur(points) / vitesseMs + 3 * Math.max(0, points.length - 2) + (2 * altitudeM) / 1.5;
}

/** Le segment [a, b] touche-t-il le bord du polygone ? */
const toucheBord = (a, b, poly) =>
  poly.some((p, i) => segmentsSeCoupent(a, b, p, poly[(i + 1) % poly.length]));

/** 6. Vérifications avant envoi : liste des problèmes (vide si tout va bien). */
export function verifierChemin(limites, zones, points, maxWaypoints) {
  const problemes = [];
  if (limites.length < 3 || !estSimple(limites)) problemes.push("limites invalides");
  if (points.length > maxWaypoints) problemes.push(`trop de waypoints (${points.length} > ${maxWaypoints})`);
  points.forEach((p, i) => {
    if (!contient(limites, p)) problemes.push(`waypoint ${i} hors des limites`);
    zones.forEach((z, j) => { if (contient(z, p)) problemes.push(`waypoint ${i} dans la zone ${j}`); });
  });
  for (let i = 0; i + 1 < points.length; i++) {
    const [a, b] = [points[i], points[i + 1]];
    if (toucheBord(a, b, limites)) problemes.push(`tronçon ${i} coupe les limites`);
    zones.forEach((z, j) => { if (toucheBord(a, b, z)) problemes.push(`tronçon ${i} traverse la zone ${j}`); });
  }
  return problemes;
}
