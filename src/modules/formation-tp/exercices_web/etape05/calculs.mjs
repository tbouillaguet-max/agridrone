// =============================================================================
// Étape 5 — calculs photographiques, passes, vérifications (voir tp/etape_05_chemin_quadrillage.md)
// Tests :  cd tp/exercices_web && npm test
// Points en mètres : { x, y } ; waypoints : { x, y, action } (0 passage, 1 début photos, 2 fin, 3 photo unique).
// =============================================================================
import { contient, estSimple, segmentsSeCoupent } from "../etape04/geometrie.mjs"; // vos fonctions de l'étape 4

const aFaire = (n) => { throw new Error(`À compléter : étape 5, exercice ${n}`); };

/**
 * 1. Prises de vue, avec le GRAND côté de l'image perpendiculaire aux passes.
 * p      : { altitudeM, recouvrementFrontalPct, recouvrementLateralPct, vitesseMaxMs, flouMaxPx }
 * camera : { capteurLargeurMm, capteurHauteurMm, focaleMm, imageLargeurPx, imageHauteurPx, intervalleMinS }
 * Renvoie { empriseLargeurM, empriseLongueurM, gsdMm, espacementPassesM, distancePhotosM, vitesseMs, expositionMaxUs }.
 */
export function prisesDeVue(p, camera) { return aFaire(1); }

/**
 * 2. Passes parallèles à x sur le rectangle [0, largeur] × [0, hauteur], à `marge`
 * des bords : n = ⌈(hauteur − 2 marge) / espacement⌉ + 1 passes réparties régulièrement
 * de y = marge à y = hauteur − marge (une seule, au milieu, si hauteur ≤ 2 marge).
 * Aller-retour en commençant en bas à gauche ; chaque passe = 2 waypoints :
 * action 1 (début des photos) puis action 2 (fin des photos).
 */
export function passesRectangle(largeurM, hauteurM, espacementM, margeM) { return aFaire(2); }

/** 3. Longueur d'un chemin (somme des tronçons). */
export function longueur(points) { return aFaire(3); }

/** 4. Nombre de photos : même règle qu'à l'étape 3 (pas `pasM`, photo finale si le reste dépasse 10 % du pas). */
export function nombrePhotos(points, pasM) { return aFaire(4); }

/** 5. Durée (s) : longueur / vitesse + 3 s par waypoint intermédiaire + montée et descente (2 × altitude / 1,5 m/s). */
export function duree(points, vitesseMs, altitudeM) { return aFaire(5); }

/**
 * 6. Vérifications avant envoi (limites, zones et points en mètres). Renvoie un
 * tableau de messages, vide si tout va bien, avec exactement ces textes :
 *   "limites invalides"                       (moins de 3 sommets ou polygone non simple)
 *   "trop de waypoints (N > MAX)"
 *   "waypoint i hors des limites", "waypoint i dans la zone j"
 *   "tronçon i coupe les limites"             (le segment i → i+1 touche un côté des limites)
 *   "tronçon i traverse la zone j"            (le segment touche un côté de la zone j)
 * dans cet ordre : limites, nombre, puis waypoints, puis tronçons.
 */
export function verifierChemin(limites, zones, points, maxWaypoints) { return aFaire(6); }

void contient; void estSimple; void segmentsSeCoupent; // (à retirer quand vous les utilisez)
