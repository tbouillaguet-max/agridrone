// =============================================================================
// Étape 4 — CORRECTION : carte IGN, tracé des limites et des zones interdites
// (référence complète : planificateur/js/carte.js et app.js)
//
// Leaflet est chargé par index.html : il fournit la variable globale `L`.
// =============================================================================
import { aire, contient, estSimple, versMetres } from "./geometrie.mjs";

// Orthophotos IGN (Géoplateforme, WMTS) : gratuites, sans clé, 20 cm en France.
const IGN_ORTHO = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
  "&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&FORMAT=image/jpeg";

// 1. La carte et son fond. maxNativeZoom 19 : au-delà, Leaflet agrandit les tuiles du niveau 19.
const carte = L.map("carte").setView([46.6, 2.4], 6);
L.tileLayer(IGN_ORTHO, { maxNativeZoom: 19, maxZoom: 22, attribution: "© IGN Géoplateforme" }).addTo(carte);

// État de la page : les polygones sont des tableaux de [lat, lon] (comme le fichier de mission).
const etat = { mode: null, enCours: [], limites: null, zones: [] };
const calque = L.layerGroup().addTo(carte); // tout ce qu'on dessine, effacé et redessiné à chaque changement
const $ = (id) => document.getElementById(id);
const message = (t) => { $("message").textContent = t; };

/** Polygone en mètres autour du premier sommet des limites (ou du tracé en cours). */
function enMetres(poly) {
  const origine = (etat.limites ?? etat.enCours)[0];
  return poly.map((p) => versMetres(origine, p));
}

function zoneValide(z) {
  if (!etat.limites) return false;
  const lim = enMetres(etat.limites);
  const zm = enMetres(z);
  return estSimple(zm) && zm.every((p) => contient(lim, p));
}

// 2. Dessin : limites en vert (rouge si invalides), zones en rouge (pointillés si invalides), tracé en cours en bleu.
function redessiner() {
  calque.clearLayers();
  if (etat.limites) {
    const ok = estSimple(enMetres(etat.limites));
    L.polygon(etat.limites, { color: ok ? "#2e7d32" : "#c62828", weight: 3, fillOpacity: 0.1 }).addTo(calque);
  }
  for (const z of etat.zones) {
    const ok = zoneValide(z);
    L.polygon(z, { color: "#d32f2f", fillOpacity: ok ? 0.4 : 0.1, dashArray: ok ? null : "6 4" }).addTo(calque);
  }
  if (etat.enCours.length) {
    L.polyline(etat.enCours, { color: "#1565c0", dashArray: "4 4" }).addTo(calque);
    for (const p of etat.enCours) L.circleMarker(p, { radius: 4, color: "#1565c0" }).addTo(calque);
  }
  afficherBilan();
}

// 3. Bilan chiffré sous la carte.
function afficherBilan() {
  if (!etat.limites) { $("bilan").textContent = "Tracez les limites du terrain."; return; }
  const lim = enMetres(etat.limites);
  const lignes = [`Limites : ${etat.limites.length} sommets, ${(aire(lim) / 10000).toFixed(2)} ha — ` +
    (estSimple(lim) ? "valides" : "INVALIDES (des côtés se croisent)")];
  etat.zones.forEach((z, i) => {
    const zm = enMetres(z);
    const dedans = zm.every((p) => contient(lim, p));
    lignes.push(`Zone ${i + 1} : ${aire(zm).toFixed(0)} m² — ${estSimple(zm) ? "simple" : "INVALIDE"}, ` +
      (dedans ? "dans les limites" : "HORS des limites"));
  });
  $("bilan").innerHTML = lignes.join("<br>");
}

// 4. Tracé : chaque clic ajoute un sommet au polygone en cours.
carte.on("click", (e) => {
  if (!etat.mode) return;
  etat.enCours.push([e.latlng.lat, e.latlng.lng]);
  redessiner();
});

function commencer(mode) {
  if (mode === "zone" && !etat.limites) { message("Tracez d'abord les limites."); return; }
  etat.mode = mode;
  etat.enCours = [];
  message(mode === "limites" ? "Cliquez les sommets des limites, puis « Terminer le tracé »." : "Cliquez les sommets de la zone.");
  redessiner();
}

function terminer() {
  if (etat.enCours.length < 3) { message("Il faut au moins 3 sommets."); return; }
  if (etat.mode === "limites") etat.limites = etat.enCours;
  else etat.zones.push(etat.enCours);
  etat.mode = null;
  etat.enCours = [];
  message("");
  redessiner();
  enregistrer();
}

// Bonus : le tracé survit au rechargement de la page (stockage local du navigateur).
function enregistrer() {
  try { localStorage.setItem("tp-etape4", JSON.stringify({ limites: etat.limites, zones: etat.zones })); } catch { /* indisponible */ }
}

$("btn-limites").onclick = () => commencer("limites");
$("btn-zone").onclick = () => commencer("zone");
$("btn-terminer").onclick = terminer;
$("btn-effacer").onclick = () => { Object.assign(etat, { mode: null, enCours: [], limites: null, zones: [] }); enregistrer(); redessiner(); };

try {
  const sauve = JSON.parse(localStorage.getItem("tp-etape4") ?? "null");
  if (sauve?.limites) {
    Object.assign(etat, sauve);
    carte.fitBounds(etat.limites);
  }
} catch { /* rien à relire */ }
redessiner();
