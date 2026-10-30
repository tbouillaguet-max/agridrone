// Outils communs aux tests : terrains construits en mètres autour d'un point.
import { ProjectionLocale } from "../js/geometrie.js";
import { CONFIG } from "../js/config.js";

export const proj = new ProjectionLocale(48.8566, 2.3522);

/** Polygone géographique à partir de sommets en mètres [[x, y], …]. */
export const geo = (sommets) => sommets.map(([x, y]) => proj.versGeo({ x, y }));
export const xy = (p) => proj.versXY(p);

export const rectangle = (l, h, x0 = 0, y0 = 0) => geo([[x0, y0], [x0 + l, y0], [x0 + l, y0 + h], [x0, y0 + h]]);

export const parametres = (modifs = {}) => ({ ...CONFIG.mission, ...modifs });
// Caméra d'essai FIXE (12 Mpx, capteur 7,2 × 5,4 mm, focale 5,4 mm, 0,7 s entre
// deux photos) : les tests ne dépendent pas des valeurs provisoires de config.js.
export const camera = {
  capteurLargeurMm: 7.2, capteurHauteurMm: 5.4, focaleMm: 5.4, imageLargeurPx: 4000, imageHauteurPx: 3000,
  intervalleMinS: 0.7, expositionMinUs: 100,
};
export const tech = { ...CONFIG.tech };
export const capacites = { ...CONFIG.capacites };
export const drone = { ...CONFIG.drone };
