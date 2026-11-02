// Vérifications avant l'envoi d'une mission à AU2. AU2 refait les contrôles
// de format et de capacité (MISSION_ACK) ; les contrôles géométriques sont faits ici.
//
// Chaque contrôle renvoie { code, intitule, etat: "ok" | "erreur" | "avertissement", detail }.
// L'envoi n'est possible que si aucun contrôle n'est en « erreur ».

import * as G from "./geometrie.js";
import { ACTION } from "./protocole.js";

export const CODE = Object.freeze({
  LIMITES: 1, ZONES: 2, NB_WAYPOINTS: 3, WAYPOINTS_DEDANS: 4, TRONCONS: 5, ALTITUDES: 6, VITESSES: 7,
  MARGES: 10, ENERGIE: 11, PHOTOS: 12, CULTURE: 13, CAMERA: 14,
});

/**
 * @param mission  { culture, limites, zones, waypoints: [{lat, lon, altitudeM, vitesseMs, action}] }
 * @param capacites { maxWaypoints, maxZones, maxSommetsLimites, maxSommetsZone, hauteurMinM, hauteurMaxM, vitesseMaxMs }
 * @param extras   { culturesAdmises, cameraProvisoire, margeLimitesM, margeZonesM, stats, prisesDeVue }
 *                 (facultatif). `culturesAdmises` (liste) active le contrôle de la culture.
 */
export function verifierMission(mission, capacites, extras = {}) {
  const r = [];
  const ajouter = (code, intitule, ok, detail = "", avertissementSeulement = false) =>
    r.push({ code, intitule, etat: ok ? "ok" : avertissementSeulement ? "avertissement" : "erreur", detail });

  // Culture : obligatoire (le pipeline d'analyse choisit son modèle d'après elle).
  if (Array.isArray(extras.culturesAdmises)) {
    const c = mission.culture;
    ajouter(CODE.CULTURE, "Culture de la parcelle choisie", extras.culturesAdmises.includes(c),
      c == null ? "choisissez la culture (blé, maïs ou pommier)"
        : extras.culturesAdmises.includes(c) ? c : `« ${c} » inconnue (${extras.culturesAdmises.join(", ")})`);
  }
  if (extras.cameraProvisoire) {
    ajouter(CODE.CAMERA, "Paramètres de la caméra", false,
      "valeurs provisoires (TO DO : modèle de caméra) : emprise et distance entre photos approximatives", true);
  }

  const limites = mission.limites ?? [];
  if (limites.length < 3) {
    ajouter(CODE.LIMITES, "Limites du terrain : polygone fermé et valide", false, "tracez au moins 3 sommets");
    return r;
  }
  const proj = G.ProjectionLocale.autourDe(limites);
  const L = limites.map((p) => proj.versXY(p));
  const aire = Math.abs(G.aireSignee(L));
  const limitesOk = L.length <= capacites.maxSommetsLimites && G.estSimple(L) && aire > 1;
  ajouter(CODE.LIMITES, "Limites du terrain : polygone fermé et valide", limitesOk,
    limitesOk ? `${L.length} sommets, ${(aire / 10000).toFixed(2)} ha`
      : L.length > capacites.maxSommetsLimites ? `${L.length} sommets (maximum ${capacites.maxSommetsLimites})`
        : "les côtés se croisent ou la surface est nulle");

  const Z = (mission.zones ?? []).map((z) => z.map((p) => proj.versXY(p)));
  const zoneFausse = Z.findIndex((z) => z.length < 3 || z.length > capacites.maxSommetsZone || !G.estSimple(z));
  ajouter(CODE.ZONES, "Zones interdites valides", Z.length <= capacites.maxZones && zoneFausse < 0,
    Z.length > capacites.maxZones ? `${Z.length} zones (maximum ${capacites.maxZones})`
      : zoneFausse >= 0 ? `zone n°${zoneFausse + 1} : 3 à ${capacites.maxSommetsZone} sommets, côtés sans croisement`
        : `${Z.length} zone(s)`);

  const wps = mission.waypoints ?? [];
  ajouter(CODE.NB_WAYPOINTS, "Nombre de waypoints compatible avec la mémoire d'AU2",
    wps.length >= 1 && wps.length <= capacites.maxWaypoints, `${wps.length} / ${capacites.maxWaypoints}`);

  const P = wps.map((w) => proj.versXY([w.lat, w.lon]));
  const dehors = limitesOk ? P.findIndex((p) => !G.contient(L, p) || Z.some((z) => G.contient(z, p))) : -1;
  ajouter(CODE.WAYPOINTS_DEDANS, "Waypoints dans les limites et hors des zones interdites",
    limitesOk && dehors < 0 && wps.length > 0, dehors >= 0 ? `waypoint n°${dehors + 1}` : "");

  let tronconFaux = -1;
  if (limitesOk) {
    for (let i = 1; i < P.length; i++) {
      if (!G.segmentDansPolygone(P[i - 1], P[i], L) || Z.some((z) => G.segmentTouchePolygone(P[i - 1], P[i], z))) {
        tronconFaux = i;
        break;
      }
    }
  }
  ajouter(CODE.TRONCONS, "Chemin entièrement dans les limites et hors des zones interdites",
    limitesOk && tronconFaux < 0 && wps.length > 0, tronconFaux > 0 ? `tronçon ${tronconFaux} → ${tronconFaux + 1}` : "");

  const horsBornes = wps.findIndex((w) => !(w.altitudeM >= capacites.hauteurMinM && w.altitudeM <= capacites.hauteurMaxM));
  ajouter(CODE.ALTITUDES, "Altitudes dans les bornes autorisées", horsBornes < 0,
    horsBornes >= 0 ? `waypoint n°${horsBornes + 1} : ${wps[horsBornes].altitudeM} m hors de ` +
      `[${capacites.hauteurMinM} ; ${capacites.hauteurMaxM}] m` : `[${capacites.hauteurMinM} ; ${capacites.hauteurMaxM}] m`);

  const vitesseFausse = wps.findIndex((w) => !(w.vitesseMs >= 0.2 && w.vitesseMs <= capacites.vitesseMaxMs) ||
    ![ACTION.PASSAGE, ACTION.DEBUT_PHOTOS, ACTION.FIN_PHOTOS, ACTION.PHOTO_UNIQUE].includes(w.action));
  ajouter(CODE.VITESSES, "Vitesses et actions valides", vitesseFausse < 0,
    vitesseFausse >= 0 ? `waypoint n°${vitesseFausse + 1}` : `≤ ${capacites.vitesseMaxMs} m/s`);

  // --- Avertissements (n'empêchent pas l'envoi) ---------------------------
  if (limitesOk && P.length > 1 && (extras.margeLimitesM > 0 || extras.margeZonesM > 0)) {
    let mini = Infinity;
    let miniZ = Infinity;
    for (let i = 1; i < P.length; i++) {
      mini = Math.min(mini, G.distanceSegmentBord(P[i - 1], P[i], L));
      for (const z of Z) miniZ = Math.min(miniZ, G.distanceSegmentBord(P[i - 1], P[i], z));
    }
    const ok = mini >= (extras.margeLimitesM ?? 0) - 0.05 && miniZ >= (extras.margeZonesM ?? 0) - 0.05;
    ajouter(CODE.MARGES, "Marges de sécurité respectées", ok,
      `${mini.toFixed(1)} m des limites` + (Z.length ? `, ${miniZ.toFixed(1)} m des zones` : ""), true);
  }
  if (extras.stats && extras.stats.utilisableWh) {
    const s = extras.stats;
    ajouter(CODE.ENERGIE, "Énergie suffisante (avec la réserve)", s.energieWh <= s.utilisableWh,
      `${s.energieWh.toFixed(1)} Wh sur ${s.utilisableWh.toFixed(1)} Wh utilisables`, true);
  }
  if (extras.prisesDeVue && extras.prisesDeVue.avertissements.length) {
    ajouter(CODE.PHOTOS, "Prises de vue", false, extras.prisesDeVue.avertissements.join(" ; "), true);
  }
  return r;
}

export const envoiPossible = (controles) => controles.every((c) => c.etat !== "erreur");
