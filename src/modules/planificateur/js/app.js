// Planificateur de mission : relie la carte, les calculs, les vérifications,
// les fichiers, l'envoi à AU2 par le câble USB et l'archivage des missions.

import { CONFIG } from "./config.js";
import { Carte } from "./carte.js";
import { calculerPrisesDeVue, formaterDuree, statistiquesChemin } from "./calculs.js";
import { genererQuadrillage } from "./quadrillage.js";
import { envoiPossible, verifierMission } from "./verifications.js";
import { ACTIONS_PROPOSEES, culturesAdmises, depuisJson, elementsMission, nouvelleMission, versJson } from "./mission.js";
import { DRAPEAU, NOMS_AVARIES, NOMS_EMETTEURS, STATUT, TYPE, decoderMessage } from "./protocole.js";
import { CanalSerie, expliquerErreur } from "./canal_serie.js";
import { AU2Simule } from "./au2_simule.js";
import { TransfertMission } from "./transfert.js";
import { archiverMission, idMissionLibre, journaliserSurDisque } from "./archivage.js";
import * as G from "./geometrie.js";

const $ = (id) => document.getElementById(id);
const CLE_BROUILLON = "agridrone-planificateur-brouillon";

const etat = {
  mission: chargerBrouillon() ?? nouvelleMission(CONFIG),
  resultat: null, // résultat du quadrillage automatique
  prisesDeVue: null,
  stats: null,
  controles: [],
  canal: null, // CanalSerie ou AU2Simule
  transfert: null,
  drapeauxAu2: null, // dernier HEARTBEAT d'AU2 (armé, en vol, mission chargée)
  envoiEnCours: false,
};

// ---------------------------------------------------------------- journal
// Chaque erreur et chaque avertissement est aussi écrit sur le disque par
// serveur_local.py (journal_planificateur.txt, à côté des missions archivées).
function journal(texte, niveau = "info") {
  const ligne = document.createElement("div");
  ligne.className = `ligne-journal ${niveau}`;
  ligne.textContent = `${new Date().toLocaleTimeString()}  ${texte}`;
  $("journal").prepend(ligne);
  while ($("journal").childElementCount > 300) $("journal").lastChild.remove();
  if (niveau === "erreur" || niveau === "avertissement") {
    journaliserSurDisque({ niveau, texte, idMission: etat?.mission?.idMission ?? null });
  }
}

function message(texte) {
  $("message").textContent = texte;
  $("message").hidden = !texte;
  clearTimeout(message.minuterie);
  if (texte) message.minuterie = setTimeout(() => { $("message").hidden = true; }, 6000);
}

// ---------------------------------------------------------------- carte
const carte = new Carte($("carte"), CONFIG, {
  mission: () => etat.mission,
  surModification: () => { annulerConfirmation(); recalculer(); },
  surMessage: message,
});

// ---------------------------------------------------------------- capacités
/** Capacités d'AU2 : celles de config.js (à aligner avec le code d'AU2). */
function capacites() {
  return { ...CONFIG.capacites };
}

// ---------------------------------------------------------------- calculs
let minuterieRecalcul = null;
function recalculerPlusTard() {
  clearTimeout(minuterieRecalcul);
  minuterieRecalcul = setTimeout(recalculer, 200);
}

function recalculer() {
  const m = etat.mission;
  const p = m.parametres;
  etat.prisesDeVue = calculerPrisesDeVue(p, m.camera, CONFIG.tech);
  etat.resultat = null;
  if (m.mode === "auto") {
    if (m.limites.length >= 3 && carte.outil !== "limites") {
      const zones = m.zones.filter((z) => z.length >= 3);
      etat.resultat = genererQuadrillage({
        limites: m.limites, zones, parametres: p, camera: m.camera, tech: CONFIG.tech, depart: m.depart,
      });
      m.waypoints = etat.resultat.ok ? etat.resultat.waypoints : [];
    } else {
      m.waypoints = [];
    }
  }
  etat.stats = statistiquesChemin(m.waypoints, {
    distancePhotosM: etat.prisesDeVue.distancePhotosM, depart: m.depart,
    retourMaison: p.finMission === "retour", drone: CONFIG.drone,
  });
  etat.controles = verifierMission(
    { culture: m.culture, limites: m.limites, zones: m.zones.filter((z) => z.length), waypoints: m.waypoints },
    capacites(), {
      culturesAdmises: culturesAdmises(CONFIG), cameraProvisoire: CONFIG.cameraProvisoire,
      margeLimitesM: p.margeLimitesM, margeZonesM: p.margeZonesM, stats: etat.stats, prisesDeVue: etat.prisesDeVue,
    },
  );
  carte.afficher();
  afficherTerrain();
  afficherCalculs();
  afficherVerifications();
  afficherWaypointsManuels();
  majBoutons();
  sauverBrouillon();
}

// ---------------------------------------------------------------- affichage
function afficherTerrain() {
  const m = etat.mission;
  const aides = {
    limites: "Cliquez sur la carte pour placer les sommets des limites ; cliquez sur le premier sommet ou « Terminer » pour fermer.",
    zone: "Cliquez pour placer les sommets de la zone interdite, puis « Terminer ». Le chemin est masqué pendant le tracé.",
    waypoints: "Cliquez pour ajouter des waypoints ; glissez-les pour les déplacer, clic droit pour les supprimer.",
    depart: "Cliquez sur l'emplacement du décollage (sert aux estimations de durée et d'énergie).",
  };
  $("aide-outil").textContent = aides[carte.outil] ??
    "Glissez les sommets pour les déplacer, clic droit pour en supprimer un, cliquez sur un petit rond pour en ajouter un.";
  document.querySelectorAll("[data-outil]").forEach((b) => b.classList.toggle("actif", b.dataset.outil === carte.outil));
  $("btn-terminer").disabled = !carte.outil;
  $("btn-annuler-point").disabled = !["limites", "zone", "waypoints"].includes(carte.outil);

  let info = "Aucune limite tracée.";
  if (m.limites.length >= 3) {
    const proj = G.ProjectionLocale.autourDe(m.limites);
    const L = m.limites.map((pt) => proj.versXY(pt));
    info = `${m.limites.length} sommets · ${(Math.abs(G.aireSignee(L)) / 10000).toFixed(2)} ha · ` +
      `périmètre ${G.perimetre(L).toFixed(0)} m`;
  } else if (m.limites.length) {
    info = `${m.limites.length} sommet(s) : continuez le tracé.`;
  }
  $("info-terrain").textContent = info;

  const liste = $("liste-zones");
  liste.replaceChildren();
  m.zones.forEach((z, i) => {
    const li = document.createElement("li");
    li.textContent = `Zone interdite ${i + 1} — ${z.length} sommets `;
    const b = document.createElement("button");
    b.textContent = "Supprimer";
    b.className = "petit";
    b.addEventListener("click", () => { m.zones.splice(i, 1); annulerConfirmation(); recalculer(); });
    li.append(b);
    liste.append(li);
  });
}

function ligneCalcul(dl, terme, valeur, classe = "") {
  const dt = document.createElement("dt");
  dt.textContent = terme;
  const dd = document.createElement("dd");
  dd.textContent = valeur;
  if (classe) dd.className = classe;
  dl.append(dt, dd);
}

function afficherCalculs() {
  const dl = $("calculs");
  dl.replaceChildren();
  const pdv = etat.prisesDeVue;
  const s = etat.stats;
  const m = etat.mission;
  ligneCalcul(dl, "Résolution au sol", `${pdv.gsdMm.toFixed(2)} mm/pixel`);
  ligneCalcul(dl, "Emprise d'une photo", `${pdv.empriseLargeurM.toFixed(1)} × ${pdv.empriseLongueurM.toFixed(1)} m`);
  ligneCalcul(dl, "Distance entre photos", `${pdv.distancePhotosM.toFixed(2)} m`);
  ligneCalcul(dl, "Espacement des passes", `${pdv.espacementPassesM.toFixed(2)} m`);
  ligneCalcul(dl, "Vitesse retenue", `${pdv.vitesseMs.toFixed(2)} m/s`);
  ligneCalcul(dl, "Exposition maximale", `${Math.round(pdv.expositionMaxUs)} µs (1/${Math.round(1e6 / pdv.expositionMaxUs)} s)`);
  if (m.mode === "auto" && etat.resultat) {
    if (etat.resultat.ok) {
      ligneCalcul(dl, "Passes", `${etat.resultat.nbPasses} (cap ${etat.resultat.capPassesDeg.toFixed(0)}°, ` +
        `${etat.resultat.nbCellules} bloc(s))`);
    } else {
      ligneCalcul(dl, "Quadrillage", etat.resultat.erreur, "erreur");
    }
  }
  ligneCalcul(dl, "Waypoints", `${m.waypoints.length} / ${capacites().maxWaypoints}`);
  ligneCalcul(dl, "Photos (estimation)", `${s.nbPhotos}`);
  ligneCalcul(dl, "Longueur du trajet", `${s.longueurM.toFixed(0)} m` + (s.transitM ? ` (+ ${s.transitM.toFixed(0)} m de transit)` : ""));
  ligneCalcul(dl, "Durée estimée", formaterDuree(s.dureeS));
  ligneCalcul(dl, "Énergie estimée", `${s.energieWh.toFixed(1)} Wh · ${Math.round(s.chargeMah ?? 0)} mAh · ` +
    `${s.pourcentBatterie.toFixed(0)} % de la batterie`, s.energieWh > s.utilisableWh ? "erreur" : "");
}

function afficherVerifications() {
  const ul = $("verifications");
  ul.replaceChildren();
  for (const c of etat.controles) {
    const li = document.createElement("li");
    li.className = c.etat;
    const icone = c.etat === "ok" ? "✔" : c.etat === "erreur" ? "✖" : "⚠";
    li.textContent = `${icone} ${c.intitule}${c.detail ? ` — ${c.detail}` : ""}`;
    ul.append(li);
  }
}

function afficherWaypointsManuels() {
  const m = etat.mission;
  $("parametres-auto").hidden = m.mode !== "auto";
  $("parametres-manuel").hidden = m.mode !== "manuel";
  if (m.mode !== "manuel") return;
  const corps = $("table-waypoints");
  corps.replaceChildren();
  m.waypoints.forEach((w, i) => {
    const tr = document.createElement("tr");
    const td = (contenu) => { const c = document.createElement("td"); c.append(contenu); tr.append(c); return c; };
    td(String(i + 1));
    const champ = (valeur, pas, appliquer) => {
      const input = document.createElement("input");
      input.type = "number";
      input.step = pas;
      input.value = valeur;
      input.addEventListener("change", () => { appliquer(Number(input.value)); annulerConfirmation(); recalculer(); });
      return input;
    };
    td(champ(w.altitudeM, "0.5", (v) => { w.altitudeM = v; }));
    td(champ(w.vitesseMs, "0.1", (v) => { w.vitesseMs = v; }));
    const select = document.createElement("select");
    for (const [code, libelle] of ACTIONS_PROPOSEES) select.add(new Option(libelle, code, false, code === w.action));
    select.addEventListener("change", () => { w.action = Number(select.value); annulerConfirmation(); recalculer(); });
    td(select);
    const sup = document.createElement("button");
    sup.textContent = "✖";
    sup.className = "petit";
    sup.title = "Supprimer ce waypoint";
    sup.addEventListener("click", () => { m.waypoints.splice(i, 1); annulerConfirmation(); recalculer(); });
    td(sup);
    corps.append(tr);
  });
}

function majBoutons() {
  const connecte = etat.canal?.connecte;
  const controlesOk = etat.mission.waypoints.length > 0 && envoiPossible(etat.controles);
  const confirme = $("confirmation").checked;
  const pret = connecte && controlesOk && confirme;
  $("btn-envoyer").disabled = !pret || etat.envoiEnCours;
  $("btn-envoyer").title = pret ? "" : !connecte ? "Connectez d'abord AU2 (câble USB) ou AU2 simulé"
    : !controlesOk ? "Corrigez les vérifications en rouge (dont la culture)"
      : "Cochez « J'ai vérifié… » après avoir relu la mission";
}

// ---------------------------------------------------------------- formulaire
function lierParametres() {
  const m = () => etat.mission;
  const lier = (id, cle, conversion = Number, objet = () => m().parametres) => {
    const el = $(id);
    const lire = () => {
      const v = el.type === "checkbox" ? el.checked : conversion(el.value);
      objet()[cle] = v;
      annulerConfirmation();
    };
    el.addEventListener("input", () => { lire(); recalculerPlusTard(); });
    el.addEventListener("change", () => { lire(); recalculer(); });
  };
  lier("p-altitude", "altitudeM");
  lier("p-altitude-manuelle", "altitudeM");
  lier("p-vitesse", "vitesseMaxMs");
  lier("p-frontal", "recouvrementFrontalPct");
  lier("p-lateral", "recouvrementLateralPct");
  lier("p-marge-limites", "margeLimitesM");
  lier("p-marge-zones", "margeZonesM");
  lier("p-transversal", "grandCoteTransversal");
  lier("p-fin", "finMission", String);
  lier("p-vitesse-manuelle", "vitesseManuelleMs");
  lier("p-action-manuelle", "actionManuelle", Number);
  $("p-cap-auto").addEventListener("change", () => {
    m().parametres.capPassesDeg = $("p-cap-auto").checked ? null : Number($("p-cap").value);
    $("p-cap").disabled = $("p-cap-auto").checked;
    recalculer();
  });
  $("p-cap").addEventListener("input", () => {
    if (!$("p-cap-auto").checked) { m().parametres.capPassesDeg = Number($("p-cap").value); recalculerPlusTard(); }
  });
  for (const cle of Object.keys(CONFIG.camera)) lier(`c-${cle}`, cle, Number, () => m().camera);
  document.querySelectorAll("input[name=mode]").forEach((r) => r.addEventListener("change", () => {
    m().mode = r.value;
    annulerConfirmation();
    if (r.value === "manuel" && !confirm("Passer en waypoints manuels ? Le chemin actuel est conservé et devient modifiable.")) {
      m().mode = "auto";
    }
    remplirFormulaire();
    recalculer();
  }));
  $("nom-mission").addEventListener("input", () => { m().nom = $("nom-mission").value; sauverBrouillon(); });
  $("p-culture").addEventListener("change", () => {
    m().culture = $("p-culture").value || null;
    annulerConfirmation();
    recalculer();
  });
}

function remplirFormulaire() {
  const m = etat.mission;
  const p = m.parametres;
  $("nom-mission").value = m.nom;
  $("p-culture").value = m.culture ?? "";
  $("p-altitude").value = p.altitudeM;
  $("p-altitude-manuelle").value = p.altitudeM;
  $("p-vitesse").value = p.vitesseMaxMs;
  $("p-frontal").value = p.recouvrementFrontalPct;
  $("p-lateral").value = p.recouvrementLateralPct;
  $("p-marge-limites").value = p.margeLimitesM;
  $("p-marge-zones").value = p.margeZonesM;
  $("p-transversal").checked = p.grandCoteTransversal !== false;
  $("p-fin").value = p.finMission;
  $("p-vitesse-manuelle").value = p.vitesseManuelleMs;
  $("p-action-manuelle").value = String(p.actionManuelle ?? 3);
  $("p-cap-auto").checked = p.capPassesDeg == null;
  $("p-cap").disabled = p.capPassesDeg == null;
  $("p-cap").value = p.capPassesDeg ?? 0;
  for (const [cle, v] of Object.entries(m.camera)) if ($(`c-${cle}`)) $(`c-${cle}`).value = v;
  document.querySelectorAll("input[name=mode]").forEach((r) => { r.checked = r.value === m.mode; });
}

// ---------------------------------------------------------------- fichiers
/** Toute modification de la mission oblige à reconfirmer avant l'envoi. */
function annulerConfirmation() {
  if ($("confirmation").checked) {
    $("confirmation").checked = false;
    majBoutons();
  }
}

function sauverBrouillon() {
  try { localStorage.setItem(CLE_BROUILLON, versJson(etat.mission)); } catch { /* stockage indisponible */ }
}

function chargerBrouillon() {
  try {
    const t = localStorage.getItem(CLE_BROUILLON);
    return t ? depuisJson(t, CONFIG) : null;
  } catch {
    return null;
  }
}

async function enregistrer() {
  const m = etat.mission;
  const texte = versJson(m);
  const nom = `${(m.nom || "mission").replace(/[^\p{L}\p{N}_-]+/gu, "_")}.json`;
  if (window.showSaveFilePicker) {
    try {
      const poignee = await window.showSaveFilePicker({
        suggestedName: nom, types: [{ description: "Mission AgriDrone", accept: { "application/json": [".json"] } }],
      });
      const f = await poignee.createWritable();
      await f.write(texte);
      await f.close();
      journal(`mission enregistrée (${poignee.name})`, "ok");
      return;
    } catch (e) {
      if (e.name === "AbortError") return;
    }
  }
  const lien = document.createElement("a");
  lien.href = URL.createObjectURL(new Blob([texte], { type: "application/json" }));
  lien.download = nom;
  lien.click();
  URL.revokeObjectURL(lien.href);
  journal(`mission enregistrée (${nom}, dossier Téléchargements)`, "ok");
}

async function ouvrirFichier(fichier) {
  try {
    etat.mission = depuisJson(await fichier.text(), CONFIG);
    annulerConfirmation();
    carte.outil = null;
    remplirFormulaire();
    recalculer();
    carte.centrerSurMission();
    journal(`mission « ${etat.mission.nom} » ouverte`, "ok");
    if (!etat.mission.culture) message("Ce fichier n'indique pas la culture : choisissez-la avant l'envoi.");
  } catch (e) {
    message(`Fichier refusé : ${e.message}`);
  }
}

// ---------------------------------------------------------------- AU2
function brancherCanal(canal, nom) {
  etat.canal = canal;
  etat.drapeauxAu2 = null;
  etat.transfert = new TransfertMission(canal, {
    delaiReponseMs: CONFIG.serie.delaiReponseMs, essais: CONFIG.serie.essais,
    essaisRelecture: CONFIG.serie.essaisRelecture, journal,
  });
  canal.ajouterEcouteur((t) => recevoir(t));
  canal.surDeconnexion = (raison) => {
    $("etat-au2").textContent = "AU2 : déconnecté";
    $("etat-au2").className = "pastille";
    $("etat-drone").textContent = raison ? `Liaison perdue : ${raison}.` : "";
    etat.drapeauxAu2 = null;
    majBoutons();
  };
  $("etat-au2").textContent = `AU2 : ${nom}`;
  $("etat-au2").className = "pastille connecte";
  $("info-au2").textContent = `Capacités attendues d'AU2 : ${CONFIG.capacites.maxWaypoints} waypoints, ` +
    `${CONFIG.capacites.maxZones} zones (config.js, à aligner avec le code d'AU2).`;
  recalculer();
}

function afficherDrapeaux(d) {
  const arme = d & DRAPEAU.ARME;
  const enVol = d & DRAPEAU.EN_VOL;
  $("etat-drone").textContent = `Drone ${enVol ? "EN VOL" : arme ? "ARMÉ" : "désarmé"} · ` +
    `mission ${d & DRAPEAU.MISSION_CHARGEE ? "chargée" : "non chargée"}` +
    (arme || enVol ? " · nouvelle mission refusée tant qu'il n'est pas posé et désarmé" : "");
  $("etat-au2").className = `pastille ${arme || enVol ? "arme" : "connecte"}`;
}

function recevoir(t) {
  let m;
  try { m = decoderMessage(t.type, t.donnees); } catch { return; }
  if (t.type === TYPE.HEARTBEAT) {
    if (m.etat !== etat.drapeauxAu2) { etat.drapeauxAu2 = m.etat; afficherDrapeaux(m.etat); }
  } else if (t.type === TYPE.ALERTE_AVARIE) {
    const nom = NOMS_AVARIES[m.code] ?? `avarie 0x${m.code.toString(16)}`;
    journal(`alerte de ${NOMS_EMETTEURS[m.source] ?? "?"} : ${nom}${m.actif ? "" : " (terminée)"}`,
      m.actif && m.gravite >= 2 ? "erreur" : m.actif ? "avertissement" : "info");
  } else if (t.type === TYPE.TEXTE) {
    journal(m.texte, ["info", "info", "avertissement", "erreur"][m.gravite] ?? "info");
  }
}

async function connecterSerie() {
  if (!CanalSerie.disponible()) {
    message("Web Serial indisponible : ouvrez cette page dans Chrome (ou Edge) sur PC, via http://localhost.");
    return;
  }
  const canal = new CanalSerie({
    debitBauds: CONFIG.serie.debitBauds, attenteDemarrageMs: CONFIG.serie.attenteDemarrageMs, journal,
  });
  try {
    $("btn-connecter").disabled = true;
    await canal.connecter();
    brancherCanal(canal, "câble USB");
  } catch (e) {
    const texte = expliquerErreur(e);
    journal(`connexion à AU2 impossible : ${texte}`, "erreur");
    message(texte);
  } finally {
    $("btn-connecter").disabled = false;
  }
}

function connecterSimulation() {
  const canal = new AU2Simule({ capacites: CONFIG.capacites, taillePaquet: 20, heartbeatMs: 500 });
  brancherCanal(canal, "simulé (aucune carte)");
  window.planificateur.au2Simule = canal; // console : planificateur.au2Simule.arme = true
  journal("AU2 simulé : la mission est stockée et relue comme sur la vraie carte", "avertissement");
}

async function envoyer() {
  const m = etat.mission;
  if (!envoiPossible(etat.controles) || !$("confirmation").checked) return;
  etat.envoiEnCours = true;
  majBoutons();
  // Nouvel identifiant à chaque envoi, sans reprendre celui d'une mission déjà archivée.
  m.idMission = await idMissionLibre((m.idMission % 0xffff) + 1);
  const vitesse = m.mode === "auto" ? etat.prisesDeVue.vitesseMs : m.parametres.vitesseManuelleMs;
  const { elements, crc } = elementsMission(m, { distancePhotosM: etat.prisesDeVue.distancePhotosM, vitesseMs: vitesse });
  $("progression").value = 0;
  $("etat-archive").textContent = "";
  try {
    const r = await etat.transfert.transferer(elements, m.idMission, crc, (phase, i, total) => {
      $("progression").value = phase === "envoi" ? (50 * i) / total : phase === "relecture" ? 50 + (50 * i) / total : 100;
      $("etat-mission").textContent = `${phase === "envoi" ? "Envoi" : phase === "relecture" ? "Relecture" : "Validation"} ` +
        `${Math.min(i + 1, total)}/${total}`;
    });
    if (r.succes) {
      $("etat-mission").textContent = `Mission ${m.idMission} chargée dans AU2 (relue et validée).`;
      $("etat-mission").className = "ok";
      message("Mission chargée dans le drone.");
      await archiver(m);
    } else {
      $("etat-mission").textContent = `Échec : ${r.message}` +
        (r.code === STATUT.ETAT_INCOMPATIBLE ? " — posez et désarmez le drone, puis renvoyez." : "");
      $("etat-mission").className = "erreur";
    }
  } catch (e) {
    journal(`envoi interrompu : ${expliquerErreur(e)}`, "erreur");
  } finally {
    etat.envoiEnCours = false;
    $("confirmation").checked = false; // la prochaine mission devra être reconfirmée
    sauverBrouillon();
    majBoutons();
  }
}

/** Archive la mission envoyée dans data\missions (entrée E3 du pipeline d'analyse). */
async function archiver(m) {
  if (!CONFIG.archivage.actif) return;
  const r = await archiverMission(m.idMission, versJson(m));
  if (r.ok) {
    $("etat-archive").textContent = `Archivée : ${r.chemin}`;
    journal(`mission archivée : ${r.chemin}`, r.suffixe ? "avertissement" : "ok");
    if (r.suffixe) {
      journal(`l'identifiant ${m.idMission} était déjà archivé avec une autre mission : suffixe ajouté ` +
        "(le pipeline devra choisir le bon fichier)", "avertissement");
    }
  } else {
    $("etat-archive").textContent = `Archivage impossible : ${r.erreur}`;
    journal(`archivage impossible : ${r.erreur}. Enregistrez la mission à la main dans drone\\missions ` +
      `sous le nom mission_${m.idMission}.json`, "erreur");
  }
}

// ---------------------------------------------------------------- démarrage
function initialiser() {
  document.querySelectorAll("[data-outil]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.outil === "waypoints" && etat.mission.mode !== "manuel") return;
    carte.definirOutil(b.dataset.outil);
  }));
  $("btn-terminer").addEventListener("click", () => carte.terminer());
  $("btn-annuler-point").addEventListener("click", () => carte.annulerDernierPoint());
  $("btn-nouveau").addEventListener("click", () => {
    if (!confirm("Effacer la mission en cours ?")) return;
    etat.mission = nouvelleMission(CONFIG);
    annulerConfirmation();
    carte.outil = null;
    remplirFormulaire();
    recalculer();
  });
  $("btn-ouvrir").addEventListener("click", () => $("fichier").click());
  $("fichier").addEventListener("change", () => { if ($("fichier").files[0]) ouvrirFichier($("fichier").files[0]); $("fichier").value = ""; });
  $("btn-enregistrer").addEventListener("click", enregistrer);
  $("btn-centrer").addEventListener("click", () => carte.centrerSurMission());
  $("btn-me-localiser").addEventListener("click", () => {
    navigator.geolocation?.getCurrentPosition((p) => carte.centrerSur(p.coords.latitude, p.coords.longitude),
      () => message("Position indisponible."));
  });
  $("btn-connecter").addEventListener("click", connecterSerie);
  $("btn-simulation").addEventListener("click", connecterSimulation);
  $("btn-envoyer").addEventListener("click", envoyer);
  $("confirmation").addEventListener("change", majBoutons);
  for (const [cle, libelle] of Object.entries(CONFIG.cultures)) $("p-culture").add(new Option(libelle, cle));
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, select, textarea")) return;
    if (e.key === "Escape") carte.terminer();
    if (e.key === "Backspace" || (e.ctrlKey && e.key === "z")) { e.preventDefault(); carte.annulerDernierPoint(); }
  });
  lierParametres();
  remplirFormulaire();
  recalculer();
  carte.centrerSurMission();
  if (!CanalSerie.disponible()) {
    $("info-au2").textContent = "Web Serial indisponible dans ce navigateur : utilisez Chrome ou Edge sur PC (ou AU2 simulé).";
  }
  if (!window.isSecureContext) {
    message("Page non sécurisée : ouvrez-la via http://localhost (lancer.bat ou lancer.sh), sinon le câble USB est inaccessible.");
  }
}

initialiser();

// Accès pour les essais automatisés (tests/navigateur) et la console du navigateur.
window.planificateur = { etat, recalculer, carte, CONFIG };
