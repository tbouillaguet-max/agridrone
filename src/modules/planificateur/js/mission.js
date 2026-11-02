// Modèle de la mission : état éditable, fichier JSON, conversion en trames.

import { ACTION, OPTION, TYPE, crc16, e7, encoderMessage } from "./protocole.js";

export const VERSION_FICHIER = 1;

/** Nouvelle mission vide, avec les paramètres par défaut de la configuration. */
export function nouvelleMission(config) {
  const maintenant = new Date().toISOString();
  return {
    version: VERSION_FICHIER,
    nom: "Nouvelle mission",
    creeLe: maintenant,
    modifieLe: maintenant,
    idMission: Math.floor(Math.random() * 0xffff) + 1,
    // Culture de la parcelle : "ble" | "mais" | "pommier" (config.cultures).
    // Obligatoire avant l'envoi ; enregistrée dans le JSON, JAMAIS transmise au
    // drone (elle ne sert qu'au pipeline d'analyse des images).
    culture: null,
    limites: [],
    zones: [],
    depart: null,
    mode: "auto", // "auto" (quadrillage) ou "manuel"
    parametres: { ...config.mission },
    camera: { ...config.camera },
    waypoints: [], // [{lat, lon, altitudeM, vitesseMs, action}]
  };
}

/** Texte JSON du fichier de mission (lisible, versionné). */
export function versJson(mission) {
  return JSON.stringify({ ...mission, modifieLe: new Date().toISOString() }, null, 2);
}

/** Cultures admises (clés de config.cultures). */
export function culturesAdmises(config) {
  return Object.keys(config.cultures ?? {});
}

/**
 * Lit un fichier JSON de mission ; lève une erreur explicite s'il est invalide.
 * Culture absente (ancien fichier) : la mission est chargée avec `culture: null`
 * et l'envoi reste bloqué tant qu'elle n'est pas choisie. Culture inconnue :
 * erreur (le fichier ne vient pas de ce planificateur ou a été modifié).
 */
export function depuisJson(texte, config) {
  let d;
  try {
    d = JSON.parse(texte);
  } catch {
    throw new Error("ce fichier n'est pas du JSON valide");
  }
  if (d.version !== VERSION_FICHIER) throw new Error(`version de fichier ${d.version} non prise en charge`);
  const point = (p) => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite) &&
    Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180;
  if (!Array.isArray(d.limites) || !d.limites.every(point)) throw new Error("limites invalides");
  if (!Array.isArray(d.zones) || !d.zones.every((z) => Array.isArray(z) && z.every(point))) {
    throw new Error("zones interdites invalides");
  }
  if (!Array.isArray(d.waypoints) || !d.waypoints.every((w) => point([w.lat, w.lon]) &&
    Number.isFinite(w.altitudeM) && Number.isFinite(w.vitesseMs) && Number.isInteger(w.action))) {
    throw new Error("waypoints invalides");
  }
  if (d.depart != null && !point(d.depart)) throw new Error("point de décollage invalide");
  const admises = culturesAdmises(config);
  if (d.culture != null && !admises.includes(d.culture)) {
    throw new Error(`culture « ${d.culture} » inconnue (valeurs admises : ${admises.join(", ")})`);
  }
  const base = nouvelleMission(config);
  return {
    ...base, ...d,
    parametres: { ...base.parametres, ...(d.parametres ?? {}) },
    camera: { ...base.camera, ...(d.camera ?? {}) },
    mode: d.mode === "manuel" ? "manuel" : "auto",
    culture: d.culture ?? null,
    idMission: Number.isInteger(d.idMission) && d.idMission > 0 && d.idMission <= 0xffff ? d.idMission : base.idMission,
  };
}

export function optionsFin(parametres) {
  if (parametres.finMission === "atterrir") return OPTION.ATTERRIR;
  if (parametres.finMission === "stationnaire") return 0;
  return OPTION.RETOUR_MAISON;
}

/**
 * Éléments de mission dans l'ordre de transfert (§ 6.5), chacun sous la forme
 * { type, champs, donnees } ; et le CRC de mission.
 */
export function elementsMission(mission, { distancePhotosM, vitesseMs }) {
  const id = mission.idMission;
  const versE7 = ([lat, lon]) => [e7(lat), e7(lon)];
  const hauteurMax = Math.min(255, Math.ceil(Math.max(...mission.waypoints.map((w) => w.altitudeM)) + 5));
  const elements = [];
  const ajouter = (type, champs) => elements.push({ type, champs, donnees: encoderMessage(type, champs) });
  ajouter(TYPE.MISSION_DEBUT, {
    id_mission: id,
    nb_waypoints: mission.waypoints.length,
    nb_sommets_limites: mission.limites.length,
    nb_zones: mission.zones.length,
    distance_photos_cm: Math.min(0xffff, Math.round(distancePhotosM * 100)),
    vitesse_cms: Math.round(vitesseMs * 100),
    options: optionsFin(mission.parametres),
    hauteur_max_m: hauteurMax,
  });
  ajouter(TYPE.MISSION_LIMITES, { id_mission: id, sommets: mission.limites.map(versE7) });
  mission.zones.forEach((z, i) => ajouter(TYPE.ZONE_INTERDITE, { id_mission: id, index_zone: i, sommets: z.map(versE7) }));
  mission.waypoints.forEach((w, i) => ajouter(TYPE.MISSION_WAYPOINT, {
    id_mission: id, index: i, latitude_e7: e7(w.lat), longitude_e7: e7(w.lon),
    altitude_relative_cm: Math.round(w.altitudeM * 100), vitesse_cms: Math.round(w.vitesseMs * 100),
    action: w.action,
  }));
  return { elements, crc: crcMission(elements) };
}

/** CRC de mission : CRC16 enchaîné sur les données de chaque élément, dans l'ordre. */
export function crcMission(elements) {
  let crc = 0xffff;
  for (const e of elements) crc = crc16(e.donnees, 0, e.donnees.length, crc);
  return crc;
}

/** Actions proposées pour un waypoint manuel. */
export const ACTIONS_PROPOSEES = [
  [ACTION.PASSAGE, "passage"],
  [ACTION.PHOTO_UNIQUE, "photo unique"],
  [ACTION.DEBUT_PHOTOS, "début des photos"],
  [ACTION.FIN_PHOTOS, "fin des photos"],
];
