// Calculs photographiques et estimations de vol.
//
// Emprise au sol d'une photo (projection d'un capteur de largeur c à travers
// une focale f, à la hauteur H) :     emprise = H × c / f
// Résolution au sol (GSD) :            GSD = emprise / nombre de pixels
// Espacement entre passes :            emprise_transversale × (1 − recouvrement latéral)
// Distance entre deux photos :         emprise_longitudinale × (1 − recouvrement frontal)
// Vitesse maximale (cadence photo) :   v ≤ distance_photos / intervalle_minimal
// Exposition maximale (flou ≤ n px) :  t ≤ n × GSD / v

import { ProjectionLocale, distance } from "./geometrie.js";
import { ACTION } from "./protocole.js";

export function calculerPrisesDeVue(parametres, camera, tech) {
  const H = parametres.altitudeM;
  const transversal = parametres.grandCoteTransversal !== false;
  const capteurT = transversal ? camera.capteurLargeurMm : camera.capteurHauteurMm;
  const capteurL = transversal ? camera.capteurHauteurMm : camera.capteurLargeurMm;
  const pixelsT = transversal ? camera.imageLargeurPx : camera.imageHauteurPx;
  const empriseLargeurM = (H * capteurT) / camera.focaleMm;
  const empriseLongueurM = (H * capteurL) / camera.focaleMm;
  const gsdM = empriseLargeurM / pixelsT;
  const espacementPassesM = empriseLargeurM * (1 - parametres.recouvrementLateralPct / 100);
  const distancePhotosM = empriseLongueurM * (1 - parametres.recouvrementFrontalPct / 100);

  const avertissements = [];
  let vitesseMs = parametres.vitesseMaxMs > 0 ? parametres.vitesseMaxMs : tech.vitesseDefautMs;
  vitesseMs = Math.min(vitesseMs, tech.vitesseMaxAbsolueMs);
  const vitesseCadenceMs = distancePhotosM / camera.intervalleMinS;
  if (vitesseMs > vitesseCadenceMs) {
    vitesseMs = vitesseCadenceMs;
    avertissements.push(`vitesse réduite à ${vitesseMs.toFixed(2)} m/s pour tenir une photo toutes les ` +
      `${camera.intervalleMinS} s`);
  }
  const expositionMaxUs = ((tech.flouMaxPx * gsdM) / vitesseMs) * 1e6;
  if (expositionMaxUs < camera.expositionMinUs) {
    avertissements.push(`flou de bougé probable : il faudrait une exposition de ${expositionMaxUs.toFixed(0)} µs`);
  }
  return {
    empriseLargeurM, empriseLongueurM, gsdMm: gsdM * 1000, espacementPassesM, distancePhotosM,
    vitesseMs, vitesseCadenceMs, expositionMaxUs, avertissements,
  };
}

/**
 * Statistiques d'un chemin : longueur, nombre de photos, durée et énergie.
 * Mêmes règles de comptage des photos que l'application (EstimationMission.kt).
 */
export function statistiquesChemin(waypoints, { distancePhotosM, depart, retourMaison, drone }) {
  if (waypoints.length === 0) {
    return { longueurM: 0, transitM: 0, nbPhotos: 0, dureeS: 0, energieWh: 0, pourcentBatterie: 0, utilisableWh: 0 };
  }
  const proj = new ProjectionLocale(waypoints[0].lat, waypoints[0].lon);
  const xy = waypoints.map((w) => proj.versXY([w.lat, w.lon]));
  let longueurM = 0;
  let dureeS = 0;
  let nbPhotos = 0;
  let enPhotos = false;
  let depuisDerniere = 0;
  const pas = distancePhotosM;
  for (let i = 0; i < waypoints.length; i++) {
    if (i > 0) {
      const l = distance(xy[i], xy[i - 1]);
      const dz = Math.abs(waypoints[i].altitudeM - waypoints[i - 1].altitudeM);
      longueurM += l;
      dureeS += Math.max(l / Math.max(waypoints[i].vitesseMs, 0.1), dz / drone.vitesseVerticaleMs);
      if (enPhotos && pas > 0) {
        depuisDerniere += l;
        while (depuisDerniere >= pas) { nbPhotos++; depuisDerniere -= pas; }
      }
    }
    switch (waypoints[i].action) {
      case ACTION.DEBUT_PHOTOS: enPhotos = true; nbPhotos++; depuisDerniere = 0; break;
      case ACTION.FIN_PHOTOS: if (enPhotos && depuisDerniere > 0.1 * pas) nbPhotos++; enPhotos = false; break;
      case ACTION.PHOTO_UNIQUE: nbPhotos++; break;
      default: break;
    }
  }
  const hMax = Math.max(...waypoints.map((w) => w.altitudeM));
  dureeS += drone.tempsParVirageS * waypoints.length + (2 * hMax) / drone.vitesseVerticaleMs +
    drone.tempsDecollageAtterrissageS;
  // Trajets depuis et vers le point de décollage, s'il est placé
  let transitM = 0;
  if (depart) {
    const d = proj.versXY(depart);
    transitM += distance(d, xy[0]);
    if (retourMaison) transitM += distance(xy[xy.length - 1], d);
    dureeS += transitM / drone.vitesseTransitMs;
  }
  const energieWh = (drone.puissanceMoyenneW * dureeS) / 3600;
  const utilisableWh = drone.capaciteBatterieWh * (1 - drone.reserveBatteriePct / 100);
  return {
    longueurM, transitM, nbPhotos, dureeS, energieWh, utilisableWh,
    pourcentBatterie: (100 * energieWh) / drone.capaciteBatterieWh,
    chargeMah: (energieWh / drone.tensionNominaleV) * 1000,
  };
}

export function formaterDuree(s) {
  const m = Math.floor(s / 60);
  const r = Math.round(s - 60 * m);
  return m > 0 ? `${m} min ${String(r).padStart(2, "0")} s` : `${r} s`;
}
