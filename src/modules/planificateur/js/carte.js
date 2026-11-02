// Carte Leaflet : fonds (orthophotos IGN…), tracé et édition des limites, des
// zones interdites, des waypoints manuels et du point de décollage, affichage
// du chemin. La carte ne garde aucun état propre : elle lit et modifie la
// mission (objet partagé avec app.js) puis appelle `surModification`.
/* global L */

import { ACTION } from "./protocole.js";

const STYLE = {
  limites: { color: "#1b7f3b", weight: 3, fillColor: "#2ea043", fillOpacity: 0.08 },
  // Pendant le tracé d'une zone (ou des limites) : contour seul, sans remplissage, et non
  // cliquable, pour bien voir l'orthophoto et que chaque clic place un sommet.
  limitesPendantTrace: { color: "#ffffff", weight: 2, dashArray: "4 4", fill: false, interactive: false },
  limitesEnCours: { color: "#1b7f3b", weight: 3, dashArray: "6 6" },
  zone: { color: "#c62828", weight: 2, fillColor: "#e53935", fillOpacity: 0.3 },
  zoneEnCours: { color: "#c62828", weight: 2, dashArray: "6 6" },
  passePhotos: { color: "#00e5ff", weight: 3, opacity: 0.95 },
  liaison: { color: "#ffb300", weight: 2, dashArray: "5 6", opacity: 0.95 },
};

export class Carte {
  constructor(element, config, { mission, surModification, surMessage }) {
    this.config = config;
    this.mission = mission; // fonction qui renvoie la mission courante
    this.surModification = surModification;
    this.surMessage = surMessage ?? (() => {});
    this.outil = null; // "limites" | "zone" | "waypoints" | "depart" | null
    this.zoneEnCours = -1;

    this.carte = L.map(element, { zoomControl: true, doubleClickZoom: false })
      .setView(config.centreParDefaut, config.zoomParDefaut);
    const fonds = {};
    for (const [nom, f] of Object.entries(config.fonds)) fonds[nom] = L.tileLayer(f.url, f.options);
    const calques = {};
    for (const [nom, c] of Object.entries(config.calques)) calques[nom] = L.tileLayer(c.url, c.options);
    Object.values(fonds)[0].addTo(this.carte);
    L.control.layers(fonds, calques, { position: "topright" }).addTo(this.carte);
    L.control.scale({ imperial: false }).addTo(this.carte);

    this.coucheTerrain = L.layerGroup().addTo(this.carte);
    this.coucheChemin = L.layerGroup().addTo(this.carte);
    this.coucheEdition = L.layerGroup().addTo(this.carte);
    this.carte.on("click", (e) => this.cliquer(e.latlng));
  }

  // ------------------------------------------------------------------ outils
  definirOutil(outil) {
    const m = this.mission();
    if (outil === "limites" && m.limites.length >= 3 &&
      !confirm("Remplacer les limites actuelles par un nouveau tracé ?")) return;
    if (outil === "limites") m.limites = [];
    if (outil === "zone") {
      m.zones.push([]);
      this.zoneEnCours = m.zones.length - 1;
    }
    this.terminerSiZoneVide(outil);
    this.outil = outil;
    this.carte.getContainer().classList.toggle("mode-trace", !!outil);
    this.surModification();
  }

  /** Termine le tracé en cours (bouton « Terminer » ou touche Échap). */
  terminer() {
    const m = this.mission();
    if (this.outil === "limites" && m.limites.length > 0 && m.limites.length < 3) {
      this.surMessage("Il faut au moins 3 sommets pour fermer les limites.");
      return;
    }
    this.terminerSiZoneVide(null);
    this.outil = null;
    this.carte.getContainer().classList.remove("mode-trace");
    this.surModification();
  }

  terminerSiZoneVide(prochainOutil) {
    const m = this.mission();
    if (this.outil === "zone" && this.zoneEnCours >= 0 && prochainOutil !== "zone") {
      const z = m.zones[this.zoneEnCours];
      if (z && z.length < 3) {
        m.zones.splice(this.zoneEnCours, 1);
        if (z.length) this.surMessage("Zone abandonnée : il faut au moins 3 sommets.");
      }
      this.zoneEnCours = -1;
    }
  }

  annulerDernierPoint() {
    const m = this.mission();
    if (this.outil === "limites") m.limites.pop();
    else if (this.outil === "zone" && this.zoneEnCours >= 0) m.zones[this.zoneEnCours].pop();
    else if (this.outil === "waypoints") m.waypoints.pop();
    this.surModification();
  }

  cliquer({ lat, lng }) {
    const m = this.mission();
    const p = [lat, lng];
    switch (this.outil) {
      case "limites":
        if (m.limites.length >= this.config.capacites.maxSommetsLimites) {
          this.surMessage(`Au plus ${this.config.capacites.maxSommetsLimites} sommets pour les limites.`);
          return;
        }
        m.limites.push(p);
        break;
      case "zone": {
        const z = m.zones[this.zoneEnCours];
        if (z.length >= this.config.capacites.maxSommetsZone) {
          this.surMessage(`Au plus ${this.config.capacites.maxSommetsZone} sommets par zone.`);
          return;
        }
        z.push(p);
        break;
      }
      case "waypoints":
        m.waypoints.push({
          lat, lon: lng, altitudeM: m.parametres.altitudeM, vitesseMs: m.parametres.vitesseManuelleMs,
          action: Number(m.parametres.actionManuelle ?? ACTION.PHOTO_UNIQUE),
        });
        break;
      case "depart":
        m.depart = p;
        this.outil = null;
        this.carte.getContainer().classList.remove("mode-trace");
        break;
      default:
        return;
    }
    this.surModification();
  }

  // --------------------------------------------------------------- affichage
  /** Redessine tout à partir de la mission (et du chemin calculé). */
  afficher() {
    const m = this.mission();
    this.coucheTerrain.clearLayers();
    this.coucheChemin.clearLayers();
    this.coucheEdition.clearLayers();

    const traceZone = this.outil === "zone";
    // Limites
    if (m.limites.length) {
      const enCours = this.outil === "limites";
      const forme = enCours && m.limites.length < 3 ? L.polyline(m.limites, STYLE.limitesEnCours)
        : L.polygon(m.limites, enCours ? { ...STYLE.limites, dashArray: "6 6" }
          : traceZone ? STYLE.limitesPendantTrace : STYLE.limites);
      forme.addTo(this.coucheTerrain);
      // Pas de poignées des limites pendant le tracé d'une zone : elles gêneraient les clics.
      if (!traceZone) this.poignees(m.limites, "sommet-limites", () => m.limites);
    }
    // Zones interdites
    m.zones.forEach((z, i) => {
      if (!z.length) return;
      const enCours = this.outil === "zone" && i === this.zoneEnCours;
      const forme = enCours && z.length < 3 ? L.polyline(z, STYLE.zoneEnCours)
        : L.polygon(z, traceZone ? { ...STYLE.zone, fillOpacity: enCours ? 0.15 : 0.3, interactive: false } : STYLE.zone);
      if (!traceZone) forme.bindTooltip(`Zone interdite ${i + 1}`);
      forme.addTo(this.coucheTerrain);
      if (!traceZone || enCours) this.poignees(z, "sommet-zone", () => m.zones[i]);
    });
    // Point de décollage
    if (m.depart) {
      const d = L.marker(m.depart, {
        draggable: true, title: "Point de décollage (estimations seulement)",
        icon: L.divIcon({ className: "marque-depart", html: "H", iconSize: [26, 26] }),
      }).addTo(this.coucheEdition);
      d.on("dragend", () => { const ll = d.getLatLng(); m.depart = [ll.lat, ll.lng]; this.surModification(); });
      d.on("contextmenu", () => { m.depart = null; this.surModification(); });
    }
    // Le chemin (passes, liaisons, waypoints) masquerait le terrain pendant le tracé
    // des limites ou d'une zone : on ne l'affiche qu'en dehors de ces tracés.
    if (this.outil !== "limites" && !traceZone) this.afficherChemin();
  }

  afficherChemin() {
    const m = this.mission();
    const w = m.waypoints;
    for (let i = 1; i < w.length; i++) {
      const photos = w[i - 1].action === ACTION.DEBUT_PHOTOS && w[i].action === ACTION.FIN_PHOTOS;
      L.polyline([[w[i - 1].lat, w[i - 1].lon], [w[i].lat, w[i].lon]], photos ? STYLE.passePhotos : STYLE.liaison)
        .addTo(this.coucheChemin);
    }
    const manuel = m.mode === "manuel";
    w.forEach((p, i) => {
      if (!manuel && i !== 0 && i !== w.length - 1 && w.length > 40) return; // allège l'affichage
      const classe = i === 0 ? "wp wp-premier" : i === w.length - 1 ? "wp wp-dernier" : "wp";
      const marque = L.marker([p.lat, p.lon], {
        draggable: manuel, title: `Waypoint ${i + 1} — ${p.altitudeM} m`,
        icon: L.divIcon({ className: classe, html: String(i + 1), iconSize: [22, 22] }),
      }).addTo(this.coucheChemin);
      if (manuel) {
        marque.on("dragend", () => { const ll = marque.getLatLng(); p.lat = ll.lat; p.lon = ll.lng; this.surModification(); });
        marque.on("contextmenu", () => { w.splice(i, 1); this.surModification(); });
      }
    });
  }

  /**
   * Poignées d'édition d'un polygone : sommets déplaçables (clic droit pour
   * supprimer) et milieux des côtés (clic pour insérer un sommet).
   */
  poignees(points, classe, liste) {
    points.forEach((p, i) => {
      const s = L.marker(p, {
        draggable: true, title: "Glisser pour déplacer, clic droit pour supprimer",
        icon: L.divIcon({ className: `poignee ${classe}`, iconSize: [12, 12] }),
      }).addTo(this.coucheEdition);
      s.on("drag", (e) => { const ll = e.target.getLatLng(); liste()[i] = [ll.lat, ll.lng]; });
      s.on("dragend", () => this.surModification());
      s.on("contextmenu", () => { liste().splice(i, 1); this.surModification(); });
      s.on("click", (e) => {
        L.DomEvent.stopPropagation(e);
        // Clic sur le premier sommet pendant le tracé : ferme le polygone
        if (i === 0 && this.outil && liste().length >= 3) this.terminer();
      });
    });
    if (points.length >= 3 || this.outil === null) {
      const n = points.length;
      for (let i = 0; i < n && n >= 2; i++) {
        const a = points[i];
        const b = points[(i + 1) % n];
        if (n === 2 && i === 1) break;
        const milieu = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        const mm = L.marker(milieu, {
          title: "Cliquer pour ajouter un sommet ici",
          icon: L.divIcon({ className: `poignee milieu ${classe}`, iconSize: [10, 10] }),
        }).addTo(this.coucheEdition);
        mm.on("click", (e) => { L.DomEvent.stopPropagation(e); liste().splice(i + 1, 0, milieu); this.surModification(); });
      }
    }
  }

  centrerSurMission() {
    const m = this.mission();
    const points = [...m.limites, ...m.zones.flat(), ...m.waypoints.map((w) => [w.lat, w.lon])];
    if (points.length) this.carte.fitBounds(L.latLngBounds(points).pad(0.15));
  }

  centrerSur(lat, lon, zoom = 17) { this.carte.setView([lat, lon], zoom); }
}
